"""管理UI向け /api/tags のレスポンス生成ロジック（IMPL-202608060837）。

旧 main/admin_tags.py のハンドラ本体・スキーマを移設したもの。Knowledge MCP のタグ管理ツール
（list_tags / create_tag / rename_tag / set_tag_description / move_tag / delete_tag）経由で処理し、
PUT は 1 リクエストを複数のツール呼び出しへ変換する。
"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel

from src.log import log_admin_operation
from src.mcp_client import KnowledgeMcpClient
from src.main import config

_client = KnowledgeMcpClient(config.KNOWLEDGE_MCP_URL)


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
