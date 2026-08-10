"""管理UI向け /api/qa・/api/categories エンドポイント（実装指示書 IMPL-202608060837 4.5 / T10, T12）。

すべて Knowledge MCP のツール経由で処理し、chatbot_db への直接書き込みは行わない（9章DoD）。
リクエストごとに MCP セッションを新規に張る（KnowledgeMcpClient、0節の決定）。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.log import log_admin_operation
from src.mcp_client import KnowledgeMcpClient

router = APIRouter(prefix="/api")

_client = KnowledgeMcpClient(
    os.environ.get("KNOWLEDGE_MCP_URL", "http://knowledge_mcp:8100/mcp")
)


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
# エンドポイント
# --------------------------------------------------------------------------- #
@router.get("/qa", response_model=QaListResponse)
async def list_qa(
    keyword: str | None = None,
    category: str | None = None,
    tag_id: list[int] | None = Query(default=None),
    limit: int = 20,
    offset: int = 0,
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


@router.get("/qa/{qa_id}", response_model=QaDetailResponse)
async def get_qa(qa_id: str) -> QaDetailResponse:
    result = await _client.call_tool("get_qa", {"qa_id": qa_id})
    return QaDetailResponse(**result)


@router.post("/qa", status_code=201, response_model=QaDetailResponse)
async def create_qa(body: QaCreateRequest) -> QaDetailResponse:
    result = await _client.call_tool("create_qa", body.model_dump(exclude_none=True))
    log_admin_operation("create", "qa", result.get("id"), body.model_dump())
    return QaDetailResponse(**result)


@router.put("/qa/{qa_id}", response_model=QaDetailResponse)
async def update_qa(qa_id: str, body: QaUpdateRequest) -> QaDetailResponse:
    # exclude_unset により「送られたフィールドのみ」を転送する
    #（tag_ids の None=変更なし / []=全解除 の区別を保つ）。
    args = {"qa_id": qa_id, **body.model_dump(exclude_unset=True)}
    result = await _client.call_tool("update_qa", args)
    log_admin_operation("update", "qa", qa_id, body.model_dump(exclude_unset=True))
    return QaDetailResponse(**result)


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories() -> CategoryListResponse:
    result = await _client.call_tool("list_categories", {})
    return CategoryListResponse(**result)
