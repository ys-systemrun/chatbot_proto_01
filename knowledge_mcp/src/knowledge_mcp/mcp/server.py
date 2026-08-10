"""MCPサーバインスタンス生成・ツール登録（実装指示書 T9, T10）。

環境変数から依存を組み立て、FastMCP サーバを構成する。
トランスポートは Streamable HTTP（ADR-0002 の具体化）。
"""

from __future__ import annotations

import json
import os
from typing import Callable

import requests
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..db.connection import Database
from ..repository.qa_management_repository import QaManagementRepository
from ..repository.qa_repository import QARepository
from ..repository.tag_repository import TagRepository
from ..services.search_service import SearchService
from .tools import register_tools


def _bedrock_embed(client, model_id: str, text: str) -> list[float]:
    """Bedrock InvokeModel API で埋め込みベクトルを取得する（IMPL-202608101616 4.2 / 3章）。

    埋め込み系モデルは Converse API の対象外のため invoke_model() を使う。
    リクエスト/レスポンス形式はモデルにより異なるため、model_id で分岐する
    （Titan Text Embeddings を既定、Cohere Embed に対応。Open Issue で確定するモデルに合わせる）。
    """
    if "cohere" in model_id.lower():
        body = {"texts": [text], "input_type": "search_document"}
        res = client.invoke_model(modelId=model_id, body=json.dumps(body))
        payload = json.loads(res["body"].read())
        return payload["embeddings"][0]
    # Amazon Titan Text Embeddings 系（既定）
    body = {"inputText": text}
    res = client.invoke_model(modelId=model_id, body=json.dumps(body))
    payload = json.loads(res["body"].read())
    return payload["embedding"]


def _make_embed_fn(
    provider: str,
    url: str | None,
    model_name: str,
    bedrock_region: str | None = None,
) -> Callable[[str], list[float]]:
    """provider に応じた embedding 呼び出し関数を生成する（IMPL-202608101616 4.2）。

    - "lmstudio"（既定）: 既存の OpenAI 互換 Embeddings API（requests）呼び出し。
    - "bedrock": boto3 bedrock-runtime の invoke_model() 呼び出し。

    呼び出し元（QARepository, QaManagementRepository）は Callable[[str], list[float]]
    という契約のみに依存するため、DI 先のコードは変更不要。
    """
    if provider == "bedrock":
        # boto3 は bedrock 利用時のみ必要な依存であるため遅延 import する。
        import boto3

        client = boto3.client("bedrock-runtime", region_name=bedrock_region)

        def embed(text: str) -> list[float]:
            return _bedrock_embed(client, model_name, text)

        return embed

    def embed(text: str) -> list[float]:
        res = requests.post(url, json={"model": model_name, "input": text})
        res.raise_for_status()
        return res.json()["data"][0]["embedding"]

    return embed


def create_server() -> FastMCP:
    database_url = os.environ["DATABASE_URL"]
    embedding_provider = os.environ.get("EMBEDDING_PROVIDER", "lmstudio")
    default_top_k = int(os.environ.get("KNOWLEDGE_MCP_DEFAULT_TOP_K", "5"))
    port = int(os.environ.get("KNOWLEDGE_MCP_PORT", "8100"))

    if embedding_provider == "bedrock":
        embedding_url = None
        embedding_model = os.environ["BEDROCK_EMBEDDING_MODEL_ID"]
        bedrock_region = os.environ.get("BEDROCK_REGION")
    else:
        embedding_url = os.environ["LMSTUDIO_EMBEDDING_URL"]
        embedding_model = os.environ["MODEL_EMBEDDING"]
        bedrock_region = None

    db = Database(database_url)
    embed_fn = _make_embed_fn(
        embedding_provider, embedding_url, embedding_model, bedrock_region
    )

    qa_repository = QARepository(db, embed_fn)
    tag_repository = TagRepository(db)
    qa_management_repository = QaManagementRepository(db, embed_fn)
    # MVP では QARepository のみ。将来 PDF/Manual Repository を append すれば拡張可能。
    search_service = SearchService([qa_repository])

    mcp = FastMCP(
        name="knowledge-mcp",
        host="0.0.0.0",
        port=port,
    )

    register_tools(
        mcp,
        search_service=search_service,
        tag_repository=tag_repository,
        qa_management_repository=qa_management_repository,
        default_top_k=default_top_k,
    )

    # ヘルスチェック（要件8 / docker healthcheck 用）
    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return mcp
