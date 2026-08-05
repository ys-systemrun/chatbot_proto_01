"""MCPサーバインスタンス生成・ツール登録（実装指示書 T9, T10）。

環境変数から依存を組み立て、FastMCP サーバを構成する。
トランスポートは Streamable HTTP（ADR-0002 の具体化）。
"""

from __future__ import annotations

import os

import requests
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..db.connection import Database
from ..repository.qa_repository import QARepository
from ..repository.tag_repository import TagRepository
from ..services.search_service import SearchService
from .tools import register_tools


def _make_embed_fn(url: str, model_name: str):
    """既存 app/src/embedding.get_embedding と同等のembedding呼び出し関数を生成する。"""

    def embed(text: str):
        res = requests.post(url, json={"model": model_name, "input": text})
        res.raise_for_status()
        return res.json()["data"][0]["embedding"]

    return embed


def create_server() -> FastMCP:
    database_url = os.environ["DATABASE_URL"]
    embedding_url = os.environ["LMSTUDIO_EMBEDDING_URL"]
    embedding_model = os.environ["MODEL_EMBEDDING"]
    default_top_k = int(os.environ.get("KNOWLEDGE_MCP_DEFAULT_TOP_K", "5"))
    port = int(os.environ.get("KNOWLEDGE_MCP_PORT", "8100"))

    db = Database(database_url)
    embed_fn = _make_embed_fn(embedding_url, embedding_model)

    qa_repository = QARepository(db, embed_fn)
    tag_repository = TagRepository(db)
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
        default_top_k=default_top_k,
    )

    # ヘルスチェック（要件8 / docker healthcheck 用）
    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return mcp
