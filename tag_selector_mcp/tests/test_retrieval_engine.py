"""RetrievalEngine の単体テスト（実装指示書 9.1）。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tag_selector_mcp.application.retrieval_engine import RetrievalEngine
from tag_selector_mcp.models.tag import TagRecord


class FakeTagRepository:
    """TagMetadataRepository のうち RetrievalEngine が使う2メソッドだけ模す。"""

    def __init__(self, tags, alias_matches):
        self._tags = tags
        self._alias_matches = alias_matches

    def all_tags(self):
        return list(self._tags)

    def find_tags_by_alias_match(self, query):
        return list(self._alias_matches)


def _tags():
    return [
        TagRecord(id=1, name="A", aliases=["a"]),
        TagRecord(id=2, name="B", aliases=[]),
        TagRecord(id=3, name="C", aliases=["c"]),
    ]


def test_confirmed_from_alias_match():
    tags = _tags()
    repo = FakeTagRepository(tags, alias_matches=[tags[0]])
    engine = RetrievalEngine(repo)
    result = engine.retrieve("aについて")
    assert [t.id for t in result.confirmed] == [1]


def test_candidates_always_all_tags():
    tags = _tags()
    # alias 一致が無い場合でも candidates は全件
    repo = FakeTagRepository(tags, alias_matches=[])
    engine = RetrievalEngine(repo)
    result = engine.retrieve("何か")
    assert result.confirmed == []
    assert sorted(t.id for t in result.candidates) == [1, 2, 3]
