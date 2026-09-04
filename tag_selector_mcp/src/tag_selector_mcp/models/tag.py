"""TagRecord / SelectedTag データモデル（実装指示書 5.1）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TagRecord:
    """hiroba_tag ⋈ hiroba_tag_alias を集約した、タグ知識ベースの1レコード。"""

    id: int
    name: str
    description: Optional[str] = None
    parent_tag_id: Optional[int] = None
    aliases: List[str] = field(default_factory=list)  # hiroba_tag_alias から集約した alias 一覧

    def to_dict(self) -> dict:
        """list_taxonomy 出力（5.8節）に沿った辞書へ変換する。"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parent_tag_id": self.parent_tag_id,
            "aliases": list(self.aliases),
        }


@dataclass
class SelectedTag:
    """select_tags が返す1件の選択結果（実装指示書 5.1 / 5.7）。"""

    id: int
    name: str
    score: float                 # 0.0〜1.0
    path: List[str] = field(default_factory=list)  # MVP時点は [name] のみ（ADR-0010）

    def to_dict(self) -> dict:
        """select_tags 出力スキーマ（5.7節）に沿った辞書へ変換する。"""
        return {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "path": list(self.path),
        }
