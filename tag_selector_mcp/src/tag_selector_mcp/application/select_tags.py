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
    ) -> List[SelectedTag]:
        retrieval_result = self._retrieval_engine.retrieve(query)
        return self._inference_engine.infer(
            query, retrieval_result, max_tags, confidence_threshold
        )
