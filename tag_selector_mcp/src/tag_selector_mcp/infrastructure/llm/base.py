"""LLMClient 抽象基底クラス（実装指示書 5.4 / T6 / ADR-0012）。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        """prompt を渡し、LLM の応答テキストをそのまま返す。

        接続失敗・タイムアウト時は例外を呼び出し元（InferenceEngine）へ送出する。
        """
        ...
