"""MCPサーバインスタンス生成・依存組み立て（実装指示書 T11）。

環境変数から依存（DB接続・LLMクライアント・各エンジン）を組み立て、FastMCP サーバを
構成する。トランスポートは Streamable HTTP（ADR-0007）。

起動時ロード・定期ポーリングの制御に必要なため、build_server() は FastMCP 本体だけでなく
TagMetadataRepository とリロード間隔も併せて返す。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..application.inference_engine import InferenceEngine
from ..application.retrieval_engine import RetrievalEngine
from ..application.select_tags import SelectTagsUseCase
from ..db.connection import Database
from ..infrastructure.llm import create_llm_client
from ..infrastructure.repository.tag_metadata_repository import TagMetadataRepository
from .tools import register_tools


@dataclass
class ServerComponents:
    mcp: FastMCP
    tag_repository: TagMetadataRepository
    reload_interval_sec: int


def build_server() -> ServerComponents:
    database_url = os.environ["DATABASE_URL"]
    llm_provider = os.environ.get("LLM_PROVIDER", "lmstudio")
    # lmstudio 用の設定（ローカル開発）。bedrock 時は不要なため get で取得する。
    chat_url = os.environ.get("LMSTUDIO_CHAT_URL")
    chat_model = os.environ.get("LMSTUDIO_CHAT_MODEL")
    # bedrock 用の設定（AWS 環境、IMPL-202608101616 4.1 / ADR-0031）。
    bedrock_model_id = os.environ.get("BEDROCK_CHAT_MODEL_ID")
    bedrock_region = os.environ.get("BEDROCK_REGION")
    reload_interval_sec = int(os.environ.get("TAXONOMY_RELOAD_INTERVAL_SEC", "300"))
    default_max_tags = int(os.environ.get("TAG_SELECTOR_DEFAULT_MAX_TAGS", "3"))
    default_confidence_threshold = float(
        os.environ.get("TAG_SELECTOR_DEFAULT_CONFIDENCE_THRESHOLD", "0.0")
    )
    port = int(os.environ.get("TAG_SELECTOR_MCP_PORT", "8200"))

    db = Database(database_url)
    tag_repository = TagMetadataRepository(db, reload_interval_sec)

    llm_client = create_llm_client(
        llm_provider,
        chat_url,
        chat_model,
        bedrock_model_id=bedrock_model_id,
        bedrock_region=bedrock_region,
    )
    retrieval_engine = RetrievalEngine(tag_repository)
    inference_engine = InferenceEngine(llm_client)
    select_tags_use_case = SelectTagsUseCase(retrieval_engine, inference_engine)

    mcp = FastMCP(
        name="tag-selector-mcp",
        host="0.0.0.0",
        port=port,
    )

    register_tools(
        mcp,
        select_tags_use_case=select_tags_use_case,
        tag_repository=tag_repository,
        default_max_tags=default_max_tags,
        default_confidence_threshold=default_confidence_threshold,
    )

    # ヘルスチェック（要件8 / docker healthcheck 用）
    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return ServerComponents(
        mcp=mcp,
        tag_repository=tag_repository,
        reload_interval_sec=reload_interval_sec,
    )


def create_server() -> FastMCP:
    """FastMCP のみを返す簡易ファクトリ（起動時ロード／ポーリングが不要な用途向け）。"""
    return build_server().mcp
