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
    # 当該行自身の検索対象フラグ（ADR-0092）。
    is_searchable: bool = True
    # 親QAの検索対象フラグ（読み取り専用の表示用項目, ADR-0093 決定6）。
    # 実効検索可否は is_searchable AND qa_is_searchable（AND合成, ADR-0092 決定3）。
    qa_is_searchable: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "qa_id": self.qa_id,
            "qa_title": self.qa_title,
            "text": self.text,
            "is_primary": self.is_primary,
            "is_searchable": self.is_searchable,
            "qa_is_searchable": self.qa_is_searchable,
        }
