"""MCPツールのハンドラ定義（実装指示書 5.5, 5.6 / T8, T17）。

search_knowledge（読み取り系）と、タグ管理ツール
list_tags / create_tag / rename_tag / move_tag / delete_tag（書き込み系, ADR-0006）を
FastMCP インスタンスへ登録する。
"""

from __future__ import annotations

from typing import List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from ..repository.tag_repository import TagRepository, TagError
from ..services.search_service import SearchService


def register_tools(
    mcp: FastMCP,
    search_service: SearchService,
    tag_repository: TagRepository,
    default_top_k: int = 5,
) -> None:
    # -------------------------------------------------------------- #
    # search_knowledge（読み取り系）
    # -------------------------------------------------------------- #
    @mcp.tool(
        name="search_knowledge",
        description="ナレッジベース（QA等）を意味検索し、関連する文書を score 降順で返す。",
    )
    def search_knowledge(
        query: str,
        top_k: int = default_top_k,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        min_score: float = 0.0,
    ) -> dict:
        documents = search_service.search(
            query, tags=tags, category=category, top_k=top_k
        )
        results = [
            doc.to_dict() for doc in documents if doc.score >= min_score
        ]
        return {"results": results}

    # -------------------------------------------------------------- #
    # タグ管理ツール（書き込み系, ADR-0006）
    # -------------------------------------------------------------- #
    @mcp.tool(
        name="list_tags",
        description="タグを木構造で返す。parent_tag_id を指定するとその配下を起点に返す。",
    )
    def list_tags(parent_tag_id: Optional[int] = None) -> dict:
        nodes = tag_repository.list_tags(parent_tag_id=parent_tag_id)
        return {"tags": [n.to_dict() for n in nodes]}

    @mcp.tool(
        name="create_tag",
        description="タグを新規作成する。parent_tag_id 指定で子タグとして作成する。",
    )
    def create_tag(name: str, parent_tag_id: Optional[int] = None) -> dict:
        try:
            node = tag_repository.create_tag(name, parent_tag_id=parent_tag_id)
        except TagError as e:
            raise ToolError(str(e))
        return node.to_dict(include_children=False)

    @mcp.tool(name="rename_tag", description="タグ名を変更する。")
    def rename_tag(tag_id: int, new_name: str) -> dict:
        try:
            node = tag_repository.rename_tag(tag_id, new_name)
        except TagError as e:
            raise ToolError(str(e))
        return node.to_dict(include_children=False)

    @mcp.tool(
        name="move_tag",
        description="タグの親を変更する。循環参照になる操作は拒否する。",
    )
    def move_tag(tag_id: int, new_parent_tag_id: Optional[int] = None) -> dict:
        try:
            node = tag_repository.move_tag(tag_id, new_parent_tag_id)
        except TagError as e:
            raise ToolError(str(e))
        return node.to_dict(include_children=False)

    @mcp.tool(
        name="delete_tag",
        description="タグを削除する。qa_tag から参照されている、または子タグを持つ場合は拒否する。",
    )
    def delete_tag(tag_id: int) -> dict:
        try:
            tag_repository.delete_tag(tag_id)
        except TagError as e:
            raise ToolError(str(e))
        return {"deleted": tag_id}
