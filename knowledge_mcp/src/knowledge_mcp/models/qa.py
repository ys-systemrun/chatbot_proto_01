"""QA管理用データモデル（実装指示書 4.1 / T1）。

QaSummary（一覧行）/ QaDetail（詳細）と、QA登録編集の業務エラー QaError を定義する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


class QaError(Exception):
    """QA登録編集の業務エラー（必須項目欠落、存在しないcategory_id/tag_ids指定、対象QA不存在等）。"""


@dataclass
class QaSummary:
    id: str
    title: str
    category: Optional[str]
    tags: List[str] = field(default_factory=list)
    hiroba_question_altered_count: int = 0
    # 検索対象フラグ（ADR-0092）。false のとき配下の主質問文行・言い換え行も検索対象外になる。
    is_searchable: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "tags": list(self.tags),
            "hiroba_question_altered_count": self.hiroba_question_altered_count,
            "is_searchable": self.is_searchable,
        }


@dataclass
class QaDetail:
    id: str
    title: str
    question_text: str
    answer_text: str
    category: Optional[dict] = None      # {"id": int, "name": str}
    tags: List[dict] = field(default_factory=list)  # [{"id": int, "name": str}, ...]
    hiroba_question_altered_count: int = 0
    is_searchable: bool = True  # 検索対象フラグ（ADR-0092）

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "question_text": self.question_text,
            "answer_text": self.answer_text,
            "category": self.category,
            "tags": list(self.tags),
            "hiroba_question_altered_count": self.hiroba_question_altered_count,
            "is_searchable": self.is_searchable,
        }
