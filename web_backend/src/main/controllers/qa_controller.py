"""管理UI向け /api/qa・/api/categories のレスポンス生成ロジック（IMPL-202608060837）。

旧 main/admin_qa.py のハンドラ本体・スキーマを移設したもの。すべて Knowledge MCP のツール経由で
処理し、chatbot_db への直接書き込みは行わない。リクエストごとに MCP セッションを新規に張る。
ルート定義（app.py）は本 Controller の関数を呼び出すだけにする。
"""

from __future__ import annotations

import csv
import io

from fastapi import HTTPException
from pydantic import BaseModel

from src.log import log_admin_operation
from src.mcp_client import KnowledgeMcpClient
from src.main import config

_client = KnowledgeMcpClient(config.KNOWLEDGE_MCP_URL)

# CSV 一括インポートで受け付ける列（IMPL-202608261022 T11 / ADR-0053）。
_QA_IMPORT_COLUMNS = ["uuid", "title", "question_text", "answer_text", "category_id", "tags"]


# --------------------------------------------------------------------------- #
# Pydantic モデル（4.2 節のJSON構造に対応）
# --------------------------------------------------------------------------- #
class QaSummaryModel(BaseModel):
    id: str
    title: str
    category: str | None = None
    tags: list[str] = []
    hiroba_question_altered_count: int = 0


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
    hiroba_question_altered_count: int = 0


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


# CSV 一括インポート（IMPL-202608261022 T11 / ADR-0053）。
class QaImportRowResult(BaseModel):
    row: int
    status: str
    qa_id: str | None = None
    error: str | None = None


class QaImportResponse(BaseModel):
    total: int
    success_count: int
    results: list[QaImportRowResult]


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


async def delete_qa(qa_id: str) -> None:
    """QA を削除する（紐づく qa_tag・question_altered もカスケード削除される, ADR-0067）。

    存在しない QA の削除は Knowledge MCP 側が QaError を送出し、グローバル例外ハンドラで
    409 にマッピングされる（本コントローラでは個別の例外処理を行わない）。
    """
    await _client.call_tool("delete_qa", {"qa_id": qa_id})
    log_admin_operation("delete", "qa", qa_id, {})


async def list_categories() -> CategoryListResponse:
    result = await _client.call_tool("list_categories", {})
    return CategoryListResponse(**result)


# --------------------------------------------------------------------------- #
# CSV 一括インポート（IMPL-202608261022 T11 / ADR-0053）
# --------------------------------------------------------------------------- #
def _parse_qa_import_csv(csv_bytes: bytes) -> list[dict]:
    """CSV（UTF-8, BOM 付き可）をパースして import_qa_batch へ渡す行データに整形する。

    列の機械的なバリデーション（必須列の存在チェック）のみをここで行い、
    業務バリデーション（必須値・タグ解決・部分更新）は Knowledge MCP に委ねる（ADR-0053）。
    列: uuid（空=新規, 既存=更新）, title, question_text, answer_text, category_id, tags（カンマ区切り）。
    """
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=422, detail="CSV は UTF-8（BOM 付き可）で保存してください。"
        )
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=422, detail="CSV のヘッダー行がありません。")
    fields = {f.strip() for f in reader.fieldnames if f}
    # 新規・更新いずれの行も許容するため、必須ヘッダーは title/question_text/answer_text とする。
    missing = [c for c in ("title", "question_text", "answer_text") if c not in fields]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"CSV に必要な列がありません: {', '.join(missing)}",
        )
    rows: list[dict] = []
    for raw in reader:
        rows.append(
            {col: (raw.get(col) or "").strip() for col in _QA_IMPORT_COLUMNS}
        )
    return rows


async def import_qa_csv(csv_bytes: bytes) -> QaImportResponse:
    """CSV をパースし、Knowledge MCP の import_qa_batch ツールを呼び出す。"""
    rows = _parse_qa_import_csv(csv_bytes)
    result = await _client.call_tool("import_qa_batch", {"rows": rows})
    log_admin_operation(
        "import", "qa", None, {"total": result.get("total", len(rows))}
    )
    return QaImportResponse(**result)
