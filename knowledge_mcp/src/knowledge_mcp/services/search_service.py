"""SearchService（実装指示書 5.4 / 要件6.4）。

複数の Repository の結果を集約し、score 降順で top_k 件に整形して返す。
MVP では QARepository のみが渡される想定だが、将来の PDF / Manual 追加を見据え、
複数 repository を渡しても動作するよう実装する。
"""

from __future__ import annotations

from typing import List, Optional

from ..models.document import Document
from ..repository.base import Repository


class SearchService:
    def __init__(self, repositories: List[Repository]):
        self.repositories = repositories

    def search(
        self,
        query: str,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Document]:
        aggregated: List[Document] = []
        for repo in self.repositories:
            aggregated.extend(
                repo.search(query, tags=tags, category=category, top_k=top_k)
            )

        aggregated.sort(key=lambda d: d.score, reverse=True)
        return aggregated[:top_k]
