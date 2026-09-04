"""TagNode データモデル（実装指示書 5.6 / ADR-0006、IMPL-202608060837 4.3 で description/aliases 拡張）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TagNode:
    id: int
    name: str
    parent_tag_id: Optional[int] = None
    description: Optional[str] = None
    # タグフォルダ（分類表示専用メタデータ、ADR-0072）。0 または 1 件（None=未分類）。
    # parent_tag_id による is-a 階層とは独立し、search_knowledge の検索には一切使わない。
    folder_id: Optional[int] = None
    # 兄弟集合（同じ parent_tag_id を持つノード）内でのローカルな表示順序（ADR-0074）。
    # 値が小さいほど先に表示される。表示専用属性であり検索・スコアには関与しない。
    display_order: Optional[float] = None
    # alias 一覧。[{"id": int, "alias": str}, ...]
    aliases: List[dict] = field(default_factory=list)
    children: List["TagNode"] = field(default_factory=list)

    def to_dict(self, include_children: bool = True) -> dict:
        """MCP出力用の辞書へ変換する。

        include_children=False の場合は単一タグ（create_tag / rename_tag / move_tag 等の戻り値）
        として children を含めない。
        """
        d = {
            "id": self.id,
            "name": self.name,
            "parent_tag_id": self.parent_tag_id,
            "description": self.description,
            "folder_id": self.folder_id,
            "display_order": self.display_order,
            "aliases": [dict(a) for a in self.aliases],
        }
        if include_children:
            d["children"] = [c.to_dict() for c in self.children]
        return d
