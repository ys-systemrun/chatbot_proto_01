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

# CSV 一括インポートで受け付ける列（IMPL-202608261630 T3 / ADR-0061、ADR-0081 で aliases 追加）。
# aliases はパイプ「|」区切りの複数エイリアスを1セルにまとめた列（任意列、追加専用）。
_TAG_IMPORT_COLUMNS = ["name", "parent_name", "description", "aliases"]

# CSV エクスポートの列（IMPL-202608281500 / ADR-0065、ADR-0081 で aliases 追加）。
# import_tag_batch（ADR-0061/0081）と完全一致させ、そのまま再インポートできる形式にする。
# export_tags は id も返すが、CSV には出力しない（upsertキーが name のため誤解防止）。
_TAG_EXPORT_COLUMNS = ["name", "parent_name", "description", "aliases"]

# aliases セル内の区切り文字（ADR-0081 決定1）。日本語同義語に含まれにくいパイプを採用する。
_ALIAS_DELIMITER = "|"


def _parse_alias_cell(raw: str | None) -> list[str]:
    """パイプ区切りの aliases セルを文字列配列へ分割する（空要素・重複を除去, ADR-0081）。"""
    result: list[str] = []
    for part in (raw or "").split(_ALIAS_DELIMITER):
        alias = part.strip()
        if alias and alias not in result:
            result.append(alias)
    return result


class TagCreateRequest(BaseModel):
    name: str
    parent_tag_id: int | None = None
    description: str | None = None
    folder_id: int | None = None  # タグフォルダ（分類表示専用, ADR-0072）


class TagUpdateRequest(BaseModel):
    # name / description / parent_tag_id / folder_id のいずれか複数を指定できる。
    # exclude_unset で「送られた項目のみ」を対応するツール呼び出しへ変換する。
    # folder_id は送られたときのみ set_tag_folder を呼ぶ（null 指定でタグフォルダを解除）。
    name: str | None = None
    description: str | None = None
    parent_tag_id: int | None = None
    folder_id: int | None = None


class TagReorderRequest(BaseModel):
    # 兄弟集合内での並べ替え方向（ADR-0074）。"up"=1つ上へ、"down"=1つ下へ。
    direction: str


# タグエイリアスの追加・編集（ADR-0080）。tag_id はパス上の文脈で、追加時のみ MCP へ渡す。
class TagAliasCreateRequest(BaseModel):
    alias: str


class TagAliasUpdateRequest(BaseModel):
    alias: str


class TagListResponse(BaseModel):
    tags: list[dict]


# タグフォルダマスタ（分類表示専用メタデータ, ADR-0072 で新設、ADR-0073 で階層化）。
class TagFolderCreateRequest(BaseModel):
    name: str
    description: str | None = None
    # 親フォルダ（ADR-0073）。省略/None でルートフォルダとして作成する。
    parent_folder_id: int | None = None


class TagFolderUpdateRequest(BaseModel):
    name: str
    description: str | None = None


class TagFolderMoveRequest(BaseModel):
    # 移動先の親フォルダ（ADR-0073）。None でルートフォルダへ移動する。
    new_parent_folder_id: int | None = None


class TagFolderListResponse(BaseModel):
    folders: list[dict]


# CSV 一括インポート（IMPL-202608261630 T3 / ADR-0061）。
class TagImportRowResult(BaseModel):
    row: int
    status: str
    tag_id: int | None = None
    error: str | None = None
    # 追加専用エイリアス登録での警告（別タグに既存 等）。1行内のエイリアス単位（ADR-0081 決定3）。
    alias_warnings: list[str] | None = None


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

    # folder_id は送られたときのみ set_tag_folder を呼ぶ（null 指定でタグフォルダを解除, ADR-0072）。
    if "folder_id" in fields:
        node = await _client.call_tool(
            "set_tag_folder",
            {"tag_id": tag_id, "folder_id": fields["folder_id"]},
        )

    log_admin_operation("update", "tag", tag_id, fields)
    return node or {}


async def delete_tag(tag_id: int) -> None:
    await _client.call_tool("delete_tag", {"tag_id": tag_id})
    log_admin_operation("delete", "tag", tag_id, {})


async def reorder_tag(tag_id: int, body: TagReorderRequest) -> dict:
    """タグを兄弟集合内で1つ上／下へ並べ替える（ADR-0074）。"""
    node = await _client.call_tool(
        "reorder_tag", {"tag_id": tag_id, "direction": body.direction}
    )
    log_admin_operation("reorder", "tag", tag_id, {"direction": body.direction})
    return node


# --------------------------------------------------------------------------- #
# タグエイリアス CRUD（ADR-0080）
# 既存の create_tag / update_tag と同じく、MCP ツール呼び出し + log_admin_operation の
# 薄い BFF（ADR-0013）。tag_id は UI 上の文脈を表すパス要素で、update/remove では使わない
# （alias_id だけで一意に解決できるため）。重複 alias は MCP 側の TagError→409。
# --------------------------------------------------------------------------- #
async def add_tag_alias(tag_id: int, body: TagAliasCreateRequest) -> dict:
    alias = await _client.call_tool(
        "add_tag_alias", {"tag_id": tag_id, "alias": body.alias}
    )
    log_admin_operation("create", "tag_alias", alias.get("id"), body.model_dump())
    return alias


async def update_tag_alias(
    tag_id: int, alias_id: int, body: TagAliasUpdateRequest
) -> dict:
    alias = await _client.call_tool(
        "update_tag_alias", {"alias_id": alias_id, "new_alias": body.alias}
    )
    log_admin_operation("update", "tag_alias", alias_id, body.model_dump())
    return alias


async def remove_tag_alias(tag_id: int, alias_id: int) -> None:
    await _client.call_tool("remove_tag_alias", {"alias_id": alias_id})
    log_admin_operation("delete", "tag_alias", alias_id, {})


# --------------------------------------------------------------------------- #
# タグフォルダマスタ（分類表示専用メタデータ, ADR-0072）
# tag と同様に Knowledge MCP のツール経由で処理する。
# --------------------------------------------------------------------------- #
async def list_tag_folders() -> TagFolderListResponse:
    result = await _client.call_tool("list_tag_folders", {})
    return TagFolderListResponse(**result)


async def create_tag_folder(body: TagFolderCreateRequest) -> dict:
    folder = await _client.call_tool(
        "create_tag_folder", body.model_dump(exclude_none=True)
    )
    log_admin_operation("create", "tag_folder", folder.get("id"), body.model_dump())
    return folder


async def update_tag_folder(folder_id: int, body: TagFolderUpdateRequest) -> dict:
    args: dict = {"folder_id": folder_id, "new_name": body.name}
    if body.description is not None:
        args["description"] = body.description
    folder = await _client.call_tool("rename_tag_folder", args)
    log_admin_operation("update", "tag_folder", folder_id, body.model_dump())
    return folder


async def move_tag_folder(folder_id: int, body: TagFolderMoveRequest) -> dict:
    """タグフォルダの親を変更する（ADR-0073）。循環参照は Knowledge MCP 側で TagError→409。"""
    folder = await _client.call_tool(
        "move_tag_folder",
        {"folder_id": folder_id, "new_parent_folder_id": body.new_parent_folder_id},
    )
    log_admin_operation("update", "tag_folder", folder_id, body.model_dump())
    return folder


async def delete_tag_folder(folder_id: int) -> None:
    await _client.call_tool("delete_tag_folder", {"folder_id": folder_id})
    log_admin_operation("delete", "tag_folder", folder_id, {})


async def reorder_tag_folder(folder_id: int, body: TagReorderRequest) -> dict:
    """タグフォルダを兄弟集合内で1つ上／下へ並べ替える（ADR-0074）。"""
    folder = await _client.call_tool(
        "reorder_tag_folder", {"folder_id": folder_id, "direction": body.direction}
    )
    log_admin_operation("reorder", "tag_folder", folder_id, {"direction": body.direction})
    return folder


# --------------------------------------------------------------------------- #
# CSV 一括インポート（IMPL-202608261630 T3 / ADR-0061）
# --------------------------------------------------------------------------- #
def _parse_tag_import_csv(csv_bytes: bytes) -> list[dict]:
    """CSV（UTF-8, BOM付き可）をパースして import_tag_batch へ渡す行データに整形する。

    列の機械的なバリデーション（必須列の存在チェック）のみをここで行い、業務バリデーション
    （name必須・循環参照チェック等）は Knowledge MCP に委ねる（ADR-0061）。
    列: name（必須）, parent_name（任意）, description（任意）, aliases（任意, パイプ区切り・
    追加専用, ADR-0081）。aliases 列が無い旧形式の CSV も引き続き受け付ける（後方互換）。
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

    rows: list[dict] = []
    for raw in reader:
        row: dict = {}
        for col in _TAG_IMPORT_COLUMNS:
            if col == "aliases":
                # パイプ区切りを配列へ（ADR-0081）。他の列と異なり list として渡す。
                row[col] = _parse_alias_cell(raw.get(col))
            else:
                row[col] = (raw.get(col) or "").strip()
        rows.append(row)
    return rows


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

    列は name/parent_name/description/aliases（import_tag_batch と完全一致）で、そのまま
    再インポートできる（ADR-0081）。aliases はパイプ「|」区切りの文字列に整形する。
    export_tags ツールは id も返すが CSV には出力しない。
    既存の全データエクスポート（chatbot_invitro_export_*）と混同しないファイル名にする（要件12章#5）。
    """
    result = await _client.call_tool("export_tags", {})
    items = result.get("items", [])

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_TAG_EXPORT_COLUMNS)
    writer.writeheader()
    for item in items:
        writer.writerow(
            {
                "name": item.get("name") or "",
                "parent_name": item.get("parent_name") or "",
                "description": item.get("description") or "",
                "aliases": _ALIAS_DELIMITER.join(item.get("aliases") or []),
            }
        )

    # Excel 互換のため UTF-8 BOM を付与する（既存の import は utf-8-sig で読めるため往復可能）。
    csv_bytes = buf.getvalue().encode("utf-8-sig")
    filename = f"tags_{_timestamp()}.csv"
    log_admin_operation("export", "tag", None, {"total": len(items)})
    return csv_bytes, filename
