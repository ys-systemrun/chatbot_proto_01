"""言い換え質問文（question_altered）管理用データモデル（IMPL-202608281100 T1 / ADR-0064）。

言い換え行（is_primary=false）を対象とした管理機能で扱う 1 行を表す QuestionAltered と、
業務エラー QuestionAlteredError を定義する。主質問文行（is_primary=true）の生成・更新は
本モデルの対象外であり、引き続き create_qa/update_qa（ADR-0014）のみが行う。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class QuestionAlteredError(Exception):
    """言い換え行の業務エラー。

    必須項目欠落・対象行の不存在・is_primary=true 行への書き込み操作・
    存在しない qa_id 指定・qa_id の付け替え指定 等で送出する。
    """


@dataclass
class QuestionAltered:
    id: int
    qa_id: str
    text: str
    is_primary: bool
    qa_title: Optional[str] = None  # 表示用（qa_original.title を結合）

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "qa_id": self.qa_id,
            "qa_title": self.qa_title,
            "text": self.text,
            "is_primary": self.is_primary,
        }
