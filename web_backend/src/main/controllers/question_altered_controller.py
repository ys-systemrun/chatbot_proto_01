"""管理UI向け /api/question_altered のレスポンス生成ロジック（IMPL-202608281100 / ADR-0064）。

言い換え行（is_primary=false）を対象とした一覧・詳細・新規作成・編集・削除・CSV一括インポート・
CSVエクスポートを、すべて Knowledge MCP のツール経由で処理する（chatbot_db への直接アクセスなし、
ADR-0013）。既存 qa_controller / tag_controller と同様、薄い BFF 層に留める。
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import BaseModel

from src.log import log_admin_operation
from src.mcp_client import KnowledgeMcpClient
from src.main import config

_client = KnowledgeMcpClient(config.KNOWLEDGE_MCP_URL)

# CSV 一括インポート・エクスポートの列（IMPL-202608281100 / ADR-0064）。
# is_primary はエクスポート時は常に false を出力し、インポート時は値を無視する（要件7.2）。
_IMPORT_COLUMNS = ["id", "qa_id", "text", "is_primary"]
_EXPORT_COLUMNS = ["id", "qa_id", "text", "is_primary"]


# --------------------------------------------------------------------------- #
# Pydantic モデル（要件7.3 のJSON構造に対応）
# --------------------------------------------------------------------------- #
class QaAlteredItem(BaseModel):
    id: int
    qa_id: str
    qa_title: str | None = None
    text: str
    is_primary: bool = False


class QaAlteredListResponse(BaseModel):
    items: list[QaAlteredItem]
    total: int


class QaAlteredDetail(BaseModel):
    id: int
    qa_id: str
    qa_title: str | None = None
    text: str
    is_primary: bool = False


class QaAlteredCreateRequest(BaseModel):
    qa_id: str
    text: str


class QaAlteredUpdateRequest(BaseModel):
    text: str


class QaAlteredImportRowResult(BaseModel):
    row: int
    status: str
    id: int | None = None
    error: str | None = None


class QaAlteredImportResponse(BaseModel):
    total: int
    success_count: int
    results: list[QaAlteredImportRowResult]


# --------------------------------------------------------------------------- #
# レスポンス生成
# --------------------------------------------------------------------------- #
async def list_items(
    qa_id: str | None,
    keyword: str | None,
    limit: int,
    offset: int,
) -> QaAlteredListResponse:
    args: dict = {"limit": limit, "offset": offset}
    if qa_id:
        args["qa_id"] = qa_id
    if keyword:
        args["keyword"] = keyword
    result = await _client.call_tool("list_question_altered", args)
    return QaAlteredListResponse(**result)


async def get_item(item_id: int) -> QaAlteredDetail:
    result = await _client.call_tool("get_question_altered", {"id": item_id})
    return QaAlteredDetail(**result)


async def create_item(body: QaAlteredCreateRequest) -> QaAlteredDetail:
    result = await _client.call_tool(
        "create_question_altered", body.model_dump()
    )
    log_admin_operation("create", "question_altered", result.get("id"), body.model_dump())
    return QaAlteredDetail(**result)


async def update_item(item_id: int, body: QaAlteredUpdateRequest) -> QaAlteredDetail:
    result = await _client.call_tool(
        "update_question_altered", {"id": item_id, "text": body.text}
    )
    log_admin_operation("update", "question_altered", item_id, body.model_dump())
    return QaAlteredDetail(**result)


async def delete_item(item_id: int) -> None:
    await _client.call_tool("delete_question_altered", {"id": item_id})
    log_admin_operation("delete", "question_altered", item_id, {})


# --------------------------------------------------------------------------- #
# CSV 一括インポート（IMPL-202608281100 / ADR-0064・0053）
# --------------------------------------------------------------------------- #
def _parse_import_csv(csv_bytes: bytes) -> list[dict]:
    """CSV（UTF-8, BOM 付き可）をパースして import_question_altered_batch へ渡す行データに整形する。

    列の機械的なバリデーション（必須列の存在チェック）のみをここで行い、業務バリデーション
    （qa_id 存在・is_primary=true 拒否・qa_id 付け替え拒否）は Knowledge MCP に委ねる（ADR-0013）。
    列: id（空=新規/既存=更新）, qa_id（新規時必須）, text（必須）, is_primary（入力は無視）。
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
    if "text" not in fields:
        raise HTTPException(status_code=422, detail="CSV に必要な列がありません: text")
    return [
        {col: (raw.get(col) or "").strip() for col in _IMPORT_COLUMNS}
        for raw in reader
    ]


async def import_csv(csv_bytes: bytes) -> QaAlteredImportResponse:
    """CSV をパースし、Knowledge MCP の import_question_altered_batch ツールを呼び出す。"""
    rows = _parse_import_csv(csv_bytes)
    result = await _client.call_tool(
        "import_question_altered_batch", {"rows": rows}
    )
    log_admin_operation(
        "import", "question_altered", None, {"total": result.get("total", len(rows))}
    )
    return QaAlteredImportResponse(**result)


# --------------------------------------------------------------------------- #
# CSV エクスポート（IMPL-202608281100 / ADR-0064）
# --------------------------------------------------------------------------- #
def _timestamp() -> str:
    """ファイル名のタイムスタンプ（Asia/Tokyo, YYYYMMDDHHmmss）。export_controller と同一方式。"""
    return datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d%H%M%S")


async def build_export_csv() -> tuple[bytes, str]:
    """is_primary=false 行の全件を CSV（UTF-8 BOM付き）に組み立て、(bytes, filename) を返す。

    列は id/qa_id/text/is_primary（is_primary は常に false）で、そのまま import_csv へ再投入できる。
    既存の全データエクスポート（chatbot_invitro_export_*）と混同しないファイル名にする（要件6.8）。
    """
    result = await _client.call_tool("export_question_altered", {})
    items = result.get("items", [])

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORT_COLUMNS)
    writer.writeheader()
    for item in items:
        writer.writerow({col: item.get(col, "") for col in _EXPORT_COLUMNS})

    # Excel 互換のため UTF-8 BOM を付与する（既存の import は utf-8-sig で読めるため往復可能）。
    csv_bytes = buf.getvalue().encode("utf-8-sig")
    filename = f"question_altered_paraphrases_{_timestamp()}.csv"
    log_admin_operation("export", "question_altered", None, {"total": len(items)})
    return csv_bytes, filename
