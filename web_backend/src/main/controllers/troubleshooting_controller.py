"""管理UI向け /api/troubleshooting_articles のレスポンス生成ロジック（ADR-0079 / REQ 9章）。

qa_controller と同様、すべて Knowledge MCP のツール経由で処理し、chatbot_db への直接書き込みは
行わない。一覧・詳細・更新（構造化フィールド編集＋タグ付け）のみを提供する。新規作成・削除は
初期スコープ外（ADR-0079 決定3。新規追加は HTML インポート処理が唯一の経路）。
"""

from __future__ import annotations

from pydantic import BaseModel

from src.log import log_admin_operation
from src.mcp_client import KnowledgeMcpClient
from src.main import config

_client = KnowledgeMcpClient(config.KNOWLEDGE_MCP_URL)


# --------------------------------------------------------------------------- #
# Pydantic モデル（9章のJSON構造に対応）
# --------------------------------------------------------------------------- #
class TroubleshootingSummaryModel(BaseModel):
    id: int
    source_key: str
    title: str
    subtitle: str | None = None
    tags: list[str] = []
    source_updated_at: str | None = None


class TroubleshootingListResponse(BaseModel):
    items: list[TroubleshootingSummaryModel]
    total: int


class TroubleshootingDetailResponse(BaseModel):
    id: int
    source_key: str
    title: str
    subtitle: str | None = None
    symptom: str | None = None
    operation_history: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    system_environment: str | None = None
    hardware_environment: str | None = None
    version_info: str | None = None
    guidance: str
    cause: str | None = None
    notes: str | None = None
    keyword_raw: str | None = None
    body_html: str = ""
    source_updated_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    tags: list[dict] = []


class TroubleshootingUpdateRequest(BaseModel):
    # 未指定フィールドは「変更なし」。tag_ids は [] で全解除、未指定で変更なし。
    # source_key / body_html / source_updated_at は編集対象外（Knowledge MCP 側でも拒否される）。
    title: str | None = None
    subtitle: str | None = None
    symptom: str | None = None
    operation_history: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    system_environment: str | None = None
    hardware_environment: str | None = None
    version_info: str | None = None
    guidance: str | None = None
    cause: str | None = None
    notes: str | None = None
    keyword_raw: str | None = None
    tag_ids: list[int] | None = None


class SourceKeyListResponse(BaseModel):
    source_keys: list[str]


# --------------------------------------------------------------------------- #
# レスポンス生成
# --------------------------------------------------------------------------- #
async def list_articles(
    keyword: str | None,
    source_key: str | None,
    tag_id: list[int] | None,
    limit: int,
    offset: int,
) -> TroubleshootingListResponse:
    args: dict = {"limit": limit, "offset": offset}
    if keyword:
        args["keyword"] = keyword
    if source_key:
        args["source_key"] = source_key
    if tag_id:
        args["tag_ids"] = tag_id
    result = await _client.call_tool("list_troubleshooting_articles", args)
    return TroubleshootingListResponse(**result)


async def get_article(article_id: int) -> TroubleshootingDetailResponse:
    result = await _client.call_tool(
        "get_troubleshooting_article", {"article_id": article_id}
    )
    return TroubleshootingDetailResponse(**result)


async def update_article(
    article_id: int, body: TroubleshootingUpdateRequest
) -> TroubleshootingDetailResponse:
    # exclude_unset で「送られたフィールドのみ」を転送する（tag_ids の None/[] 区別を保つ）。
    sent = body.model_dump(exclude_unset=True)
    tag_present = "tag_ids" in sent
    tag_ids = sent.pop("tag_ids", None)

    args: dict = {"article_id": article_id}
    if sent:
        args["fields"] = sent  # 構造化フィールドの部分更新
    if tag_present:
        args["tag_ids"] = tag_ids

    result = await _client.call_tool("update_troubleshooting_article", args)
    log_admin_operation(
        "update", "troubleshooting_article", article_id, body.model_dump(exclude_unset=True)
    )
    return TroubleshootingDetailResponse(**result)


async def list_source_keys() -> SourceKeyListResponse:
    result = await _client.call_tool("list_troubleshooting_source_keys", {})
    return SourceKeyListResponse(**result)
