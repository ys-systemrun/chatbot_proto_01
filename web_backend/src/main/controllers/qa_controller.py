"""管理UI向け /api/qa・/api/categories のレスポンス生成ロジック（IMPL-202608060837）。

旧 main/admin_qa.py のハンドラ本体・スキーマを移設したもの。すべて Knowledge MCP のツール経由で
処理し、chatbot_db への直接書き込みは行わない。リクエストごとに MCP セッションを新規に張る。
ルート定義（app.py）は本 Controller の関数を呼び出すだけにする。
"""

from __future__ import annotations

from pydantic import BaseModel

from src.log import log_admin_operation
from src.mcp_client import KnowledgeMcpClient
from src.main import config

_client = KnowledgeMcpClient(config.KNOWLEDGE_MCP_URL)


# --------------------------------------------------------------------------- #
# Pydantic モデル（4.2 節のJSON構造に対応）
# --------------------------------------------------------------------------- #
class QaSummaryModel(BaseModel):
    id: str
    title: str
    category: str | None = None
    tags: list[str] = []
    question_altered_count: int = 0


class QaListResponse(BaseModel):
    items: list[QaSummaryModel]
    total: int


class QaDetailResponse(BaseModel):
    id: str
    title: str
    question_text: str
    answer_text: str
    category: dict | None = None
    tags: list[dict] = []
    question_altered_count: int = 0


class QaCreateRequest(BaseModel):
    title: str
    question_text: str
    answer_text: str
    category_id: int | None = None
    tag_ids: list[int] | None = None


class QaUpdateRequest(BaseModel):
    # 未指定フィールドは「変更なし」。tag_ids は [] で全解除、未指定で変更なし。
    title: str | None = None
    question_text: str | None = None
    answer_text: str | None = None
    category_id: int | None = None
    tag_ids: list[int] | None = None


class CategoryModel(BaseModel):
    id: int
    name: str


class CategoryListResponse(BaseModel):
    categories: list[CategoryModel]


# --------------------------------------------------------------------------- #
# レスポンス生成
# --------------------------------------------------------------------------- #
async def list_qa(
    keyword: str | None,
    category: str | None,
    tag_id: list[int] | None,
    limit: int,
    offset: int,
) -> QaListResponse:
    args: dict = {"limit": limit, "offset": offset}
    if keyword:
        args["keyword"] = keyword
    if category:
        args["category"] = category
    if tag_id:
        args["tag_ids"] = tag_id
    result = await _client.call_tool("list_qa", args)
    return QaListResponse(**result)


async def get_qa(qa_id: str) -> QaDetailResponse:
    result = await _client.call_tool("get_qa", {"qa_id": qa_id})
    return QaDetailResponse(**result)


async def create_qa(body: QaCreateRequest) -> QaDetailResponse:
    result = await _client.call_tool("create_qa", body.model_dump(exclude_none=True))
    log_admin_operation("create", "qa", result.get("id"), body.model_dump())
    return QaDetailResponse(**result)


async def update_qa(qa_id: str, body: QaUpdateRequest) -> QaDetailResponse:
    # exclude_unset により「送られたフィールドのみ」を転送する
    #（tag_ids の None=変更なし / []=全解除 の区別を保つ）。
    args = {"qa_id": qa_id, **body.model_dump(exclude_unset=True)}
    result = await _client.call_tool("update_qa", args)
    log_admin_operation("update", "qa", qa_id, body.model_dump(exclude_unset=True))
    return QaDetailResponse(**result)


async def list_categories() -> CategoryListResponse:
    result = await _client.call_tool("list_categories", {})
    return CategoryListResponse(**result)
