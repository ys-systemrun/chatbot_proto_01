"""RetrievalEngine（実装指示書 5.3 / T5 / ADR-0009）。

MVP では Embedding 層・階層探索を実装せず、Alias 辞書によるルールベース照合のみを行う。
将来 Embedding 層・階層探索を追加する際も、本エンジン以降（InferenceEngine 等）の
インターフェースを変更せずに済むよう、候補集合を RetrievalResult として束ねて返す。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..infrastructure.repository.tag_metadata_repository import TagMetadataRepository
from ..models.tag import TagRecord


@dataclass
class RetrievalResult:
    confirmed: List[TagRecord]    # alias 一致で確定したタグ
    candidates: List[TagRecord]   # Inference Engine へ渡す全タグ候補（MVPでは全件、ADR-0009）


class RetrievalEngine:
    def __init__(self, tag_repository: TagMetadataRepository):
        self._tag_repository = tag_repository

    def retrieve(
        self, query: str, alias_match_text: str | None = None
    ) -> RetrievalResult:
        """
        1. tag_repository.find_tags_by_alias_match(alias_match_text or query) の結果を
           confirmed とする（ADR-0086。alias_match_text 省略時は query にフォールバック）。
        2. candidates は tag_repository.all_tags() の全件とする（Embedding による絞り込みは
           行わない）。candidates は query に依存しない全件取得のままとする。
        """
        confirmed = self._tag_repository.find_tags_by_alias_match(
            alias_match_text or query
        )
        candidates = self._tag_repository.all_tags()
        return RetrievalResult(confirmed=confirmed, candidates=candidates)
