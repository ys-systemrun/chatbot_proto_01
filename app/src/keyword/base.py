"""KeywordExtractor のインターフェース定義。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class KeywordExtractor(Protocol):
    """テキストからキーワードのリストを抽出するインターフェース。

    実装は extract() の 1 メソッドのみを持てばよい。
    """

    def extract(self, text: str) -> list[str]:
        """テキストから重要なキーワードを抽出して返す。

        Args:
            text: キーワードを抽出する対象テキスト。

        Returns:
            抽出されたキーワードのリスト。抽出できなかった場合は空リスト。
        """
        ...
