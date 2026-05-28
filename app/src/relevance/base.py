from __future__ import annotations

from abc import ABC, abstractmethod


class RelevanceStrategy(ABC):
    """検索結果が質問に適合するかを判定するストラテジーの基底クラス。"""

    @abstractmethod
    def is_relevant(self, question: str, results: list) -> bool:
        """
        Args:
            question: ユーザーの質問テキスト。
            results:  DB.search_similar の返り値
                      (question, answer, question_original, qa_id, distance) のリスト。
        Returns:
            適合する情報が存在すると判定した場合 True。
        """
        ...
