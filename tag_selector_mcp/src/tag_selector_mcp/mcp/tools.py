"""MCPツールのハンドラ定義（実装指示書 5.7, 5.8 / T9, T10）。

select_tags（タグ選択）、list_taxonomy / reload_taxonomy（タグ知識ベースの参照・再読込）を
FastMCP インスタンスへ登録する。エラーは Knowledge MCP と同様に ToolError（MCPエラー
レスポンス）へ変換して返す。
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from ..application.select_tags import SelectTagsUseCase
from ..infrastructure.repository.tag_metadata_repository import TagMetadataRepository

logger = logging.getLogger(__name__)


def register_tools(
    mcp: FastMCP,
    select_tags_use_case: SelectTagsUseCase,
    tag_repository: TagMetadataRepository,
    default_max_tags: int = 3,
    default_confidence_threshold: float = 0.0,
) -> None:
    # -------------------------------------------------------------- #
    # select_tags
    # -------------------------------------------------------------- #
    @mcp.tool(
        name="select_tags",
        description=(
            "質問文に最も関連するタグを選択し、id/name/score/path を score 降順で返す。"
        ),
    )
    def select_tags(
        query: str,
        max_tags: int = default_max_tags,
        confidence_threshold: float = default_confidence_threshold,
    ) -> dict:
        try:
            selected = select_tags_use_case.execute(
                query,
                max_tags=max_tags,
                confidence_threshold=confidence_threshold,
            )
        except Exception as e:
            # LLM接続失敗・DB参照失敗等はMCPエラーレスポンスへ変換する。
            logger.exception("select_tags failed")
            raise ToolError(f"select_tags failed: {e}")
        return {"selected": [s.to_dict() for s in selected]}

    # -------------------------------------------------------------- #
    # list_taxonomy（ADR-0011）
    # -------------------------------------------------------------- #
    @mcp.tool(
        name="list_taxonomy",
        description="現在キャッシュしているタグ知識ベース（id/name/description/parent_tag_id/aliases）を返す。",
    )
    def list_taxonomy() -> dict:
        tags = tag_repository.all_tags()
        return {"tags": [t.to_dict() for t in tags]}

    # -------------------------------------------------------------- #
    # reload_taxonomy（ADR-0011）
    # -------------------------------------------------------------- #
    @mcp.tool(
        name="reload_taxonomy",
        description="タグ知識ベースをDBから再読込し、リロード後のタグ件数を返す。",
    )
    def reload_taxonomy() -> dict:
        try:
            tag_repository.reload()
        except Exception as e:
            # DBアクセス失敗時は既存キャッシュを維持したままMCPエラーを返す（5.2節）。
            raise ToolError(f"reload_taxonomy failed: {e}")
        return {"reloaded": True, "tag_count": tag_repository.tag_count()}
