"""Repository 抽象基底クラス（実装指示書 5.2 / 要件6.2）。

将来 PDF / Manual 等の別ソースを追加する際、この抽象に準拠した Repository を実装すれば
SearchService / search_knowledge を変更せずに検索対象へ組み込める。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..models.document import Document


class Repository(ABC):
    @abstractmethod
    def search(
        self,
        query: str,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Document]:
        ...
