from __future__ import annotations

from .base import RelevanceStrategy

DEFAULT_THRESHOLD = 0.3


class DistanceRelevanceStrategy(RelevanceStrategy):
    """top-1 のコサイン距離が閾値未満であれば適合とみなすストラテジー。"""

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    def is_relevant(self, question: str, results: list) -> bool:
        if not results:
            return False
        top1_distance = results[0][4]
        return top1_distance < self._threshold
