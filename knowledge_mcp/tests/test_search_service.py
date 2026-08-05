"""SearchService の単体テスト（実装指示書 9.1）。

複数Repositoryを渡した場合の集約・score降順ソート・top_k切り詰めを検証する。
モックRepositoryを用い、DB非依存でテストする。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from knowledge_mcp.models.document import Document
from knowledge_mcp.repository.base import Repository
from knowledge_mcp.services.search_service import SearchService


class FakeRepository(Repository):
    def __init__(self, docs, capture=None):
        self._docs = docs
        self._capture = capture

    def search(self, query, tags=None, category=None, top_k=5):
        if self._capture is not None:
            self._capture.append(
                {"query": query, "tags": tags, "category": category, "top_k": top_k}
            )
        return list(self._docs)


def _doc(id_, score):
    return Document(
        id=id_, source_type="qa", title=id_, content="", score=score, metadata={}
    )


def test_aggregates_and_sorts_descending():
    repo_a = FakeRepository([_doc("a", 0.2), _doc("b", 0.9)])
    repo_b = FakeRepository([_doc("c", 0.5)])
    service = SearchService([repo_a, repo_b])

    results = service.search("q", top_k=10)

    assert [d.id for d in results] == ["b", "c", "a"]


def test_trims_to_top_k():
    repo = FakeRepository([_doc("a", 0.9), _doc("b", 0.8), _doc("c", 0.7)])
    service = SearchService([repo])

    results = service.search("q", top_k=2)

    assert [d.id for d in results] == ["a", "b"]


def test_passes_filters_to_each_repository():
    captured = []
    repo = FakeRepository([], capture=captured)
    service = SearchService([repo])

    service.search("q", tags=["t1"], category="cat", top_k=3)

    assert captured == [
        {"query": "q", "tags": ["t1"], "category": "cat", "top_k": 3}
    ]


def test_new_repository_without_changing_service():
    """ダミーRepository追加だけで検索対象を増やせること（要件DoD）。"""
    qa_like = FakeRepository([_doc("qa1", 0.6)])
    dummy = FakeRepository([_doc("pdf1", 0.95)])
    service = SearchService([qa_like, dummy])

    results = service.search("q", top_k=5)

    assert results[0].id == "pdf1"
    assert {d.id for d in results} == {"qa1", "pdf1"}
