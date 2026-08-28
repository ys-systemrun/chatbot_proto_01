"""管理UI向け /api/tags のレスポンス生成ロジック（IMPL-202608060837）。

旧 main/admin_tags.py のハンドラ本体・スキーマを移設したもの。Knowledge MCP のタグ管理ツール
（list_tags / create_tag / rename_tag / set_tag_description / move_tag / delete_tag）経由で処理し、
PUT は 1 リクエストを複数のツール呼び出しへ変換する。
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

# CSV 一括インポートで受け付ける列（IMPL-202608261630 T3 / ADR-0061）。
_TAG_IMPORT_COLUMNS = ["name", "parent_name", "description"]

# CSV エクスポートの列（IMPL-202608281500 / ADR-0065）。
# import_tag_batch（ADR-0061）と完全一致させ、そのまま再インポートできる形式にする。
# export_tags は id も返すが、CSV には出力しない（upsertキーが name のため誤解防止）。
_TAG_EXPORT_COLUMNS = ["name", "parent_name", "description"]


class TagCreateRequest(BaseModel):
    name: str
    parent_tag_id: int | None = None
    description: str | None = None


class TagUpdateRequest(BaseModel):
    # name / description / parent_tag_id のいずれか複数を指定できる。
    # exclude_unset で「送られた項目のみ」を対応するツール呼び出しへ変換する。
    name: str | None = None
    description: str | None = None
    parent_tag_id: int | None = None


class TagListResponse(BaseModel):
    tags: list[dict]


# CSV 一括インポート（IMPL-202608261630 T3 / ADR-0061）。
class TagImportRowResult(BaseModel):
    row: int
    status: str
    tag_id: int | None = None
    error: str | None = None


class TagImportResponse(BaseModel):
    total: int
    success_count: int
    results: list[TagImportRowResult]


async def list_tags(parent_tag_id: int | None) -> TagListResponse:
    args = {} if parent_tag_id is None else {"parent_tag_id": parent_tag_id}
    result = await _client.call_tool("list_tags", args)
    return TagListResponse(**result)


async def create_tag(body: TagCreateRequest) -> dict:
    node = await _client.call_tool("create_tag", body.model_dump(exclude_none=True))
    log_admin_operation("create", "tag", node.get("id"), body.model_dump())
    return node


async def update_tag(tag_id: int, body: TagUpdateRequest) -> dict:
    """name/description/parent_tag_id の指定に応じて必要なツールを順に呼び出す。

    Knowledge MCP 側は単一項目ごとのツールのため、web_backend 側で 1 回の PUT から
    複数ツール呼び出しへ変換する（4.6節）。
    """
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")

    node: dict | None = None
    if "name" in fields:
        args = {"tag_id": tag_id, "new_name": fields["name"]}
        if "description" in fields:
            args["description"] = fields["description"]
        node = await _client.call_tool("rename_tag", args)
    elif "description" in fields:
        node = await _client.call_tool(
            "set_tag_description",
            {"tag_id": tag_id, "description": fields["description"]},
        )

    if "parent_tag_id" in fields:
        node = await _client.call_tool(
            "move_tag",
            {"tag_id": tag_id, "new_parent_tag_id": fields["parent_tag_id"]},
        )

    log_admin_operation("update", "tag", tag_id, fields)
    return node or {}


async def delete_tag(tag_id: int) -> None:
    await _client.call_tool("delete_tag", {"tag_id": tag_id})
    log_admin_operation("delete", "tag", tag_id, {})


# --------------------------------------------------------------------------- #
# CSV 一括インポート（IMPL-202608261630 T3 / ADR-0061）
# --------------------------------------------------------------------------- #
def _parse_tag_import_csv(csv_bytes: bytes) -> list[dict]:
    """CSV（UTF-8, BOM付き可）をパースして import_tag_batch へ渡す行データに整形する。

    列の機械的なバリデーション（必須列の存在チェック）のみをここで行い、業務バリデーション
    （name必須・循環参照チェック等）は Knowledge MCP に委ねる（ADR-0061）。
    列: name（必須）, parent_name（任意）, description（任意）。
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
    if "name" not in fields:
        raise HTTPException(status_code=422, detail="CSV に必要な列がありません: name")
    return [
        {col: (raw.get(col) or "").strip() for col in _TAG_IMPORT_COLUMNS}
        for raw in reader
    ]


async def import_tags_csv(csv_bytes: bytes) -> TagImportResponse:
    """CSV をパースし、Knowledge MCP の import_tag_batch ツールを呼び出す。"""
    rows = _parse_tag_import_csv(csv_bytes)
    result = await _client.call_tool("import_tag_batch", {"rows": rows})
    log_admin_operation("import", "tag", None, {"total": result.get("total", len(rows))})
    return TagImportResponse(**result)


# --------------------------------------------------------------------------- #
# CSV エクスポート（IMPL-202608281500 / ADR-0065）
# --------------------------------------------------------------------------- #
def _timestamp() -> str:
    """ファイル名のタイムスタンプ（Asia/Tokyo, YYYYMMDDHHmmss）。export_controller と同一方式。"""
    return datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d%H%M%S")


async def build_export_csv() -> tuple[bytes, str]:
    """全タグを CSV（UTF-8 BOM付き）に組み立て、(bytes, filename) を返す。

    列は name/parent_name/description（import_tag_batch と完全一致）で、そのまま再インポートできる。
    export_tags ツールは id も返すが CSV には出力しない。エイリアスは対象外（ADR-0065）。
    既存の全データエクスポート（chatbot_invitro_export_*）と混同しないファイル名にする（要件12章#5）。
    """
    result = await _client.call_tool("export_tags", {})
    items = result.get("items", [])

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_TAG_EXPORT_COLUMNS)
    writer.writeheader()
    for item in items:
        writer.writerow(
            {col: (item.get(col) or "") for col in _TAG_EXPORT_COLUMNS}
        )

    # Excel 互換のため UTF-8 BOM を付与する（既存の import は utf-8-sig で読めるため往復可能）。
    csv_bytes = buf.getvalue().encode("utf-8-sig")
    filename = f"tags_{_timestamp()}.csv"
    log_admin_operation("export", "tag", None, {"total": len(items)})
    return csv_bytes, filename
