"""SelectTagsUseCase（実装指示書 5.6 / T8 / 要件6.1）。

RetrievalEngine（Alias照合）→ InferenceEngine（LLM選択）を束ねるユースケース。
"""

from __future__ import annotations

from typing import List

from ..models.tag import SelectedTag
from .inference_engine import InferenceEngine
from .retrieval_engine import RetrievalEngine


class SelectTagsUseCase:
    def __init__(
        self,
        retrieval_engine: RetrievalEngine,
        inference_engine: InferenceEngine,
    ):
        self._retrieval_engine = retrieval_engine
        self._inference_engine = inference_engine

    def execute(
        self,
        query: str,
        max_tags: int = 3,
        confidence_threshold: float = 0.0,
        alias_match_text: str | None = None,
    ) -> List[SelectedTag]:
        # alias_match_text は Alias 一致（確定タグ）専用の生テキスト。省略時は query に
        # フォールバックする（ADR-0086）。LLM 推論には従来通り query を使う。
        retrieval_result = self._retrieval_engine.retrieve(
            query, alias_match_text=alias_match_text
        )
        return self._inference_engine.infer(
            query, retrieval_result, max_tags, confidence_threshold
        )
