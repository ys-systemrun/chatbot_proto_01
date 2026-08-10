"""TagMetadataRepository の単体テスト（実装指示書 9.1）。

DB非依存のインメモリ Fake DB で load/reload/参照系を検証する。
"""

import os
import sys
from contextlib import contextmanager

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tag_selector_mcp.infrastructure.repository.tag_metadata_repository import (
    TagMetadataRepository,
)


# --------------------------------------------------------------------------- #
# インメモリ Fake DB
#   rows: list[(id, name, description, parent_tag_id, aliases[list])]
#   load() が発行する集約クエリの結果としてそのまま返す。
# --------------------------------------------------------------------------- #
class FakeCursor:
    def __init__(self, store):
        self.s = store
        self._result = []

    def execute(self, sql, params=None):
        if self.s.get("fail"):
            raise RuntimeError("simulated DB failure")
        self._result = list(self.s["rows"])

    def fetchall(self):
        return list(self._result)


class FakeDatabase:
    def __init__(self):
        self.store = {"rows": [], "fail": False}

    @contextmanager
    def cursor(self):
        yield FakeCursor(self.store)


@pytest.fixture
def db():
    return FakeDatabase()


@pytest.fixture
def repo(db):
    return TagMetadataRepository(db, reload_interval_sec=300)


def test_load_builds_cache(db, repo):
    db.store["rows"] = [
        (3, "積算システム", "積算の説明", None, ["積算", "歩掛"]),
        (12, "操作方法", None, 3, ["使い方"]),
    ]
    repo.load()
    assert repo.tag_count() == 2
    rec = repo.get(3)
    assert rec.name == "積算システム"
    assert rec.description == "積算の説明"
    assert rec.parent_tag_id is None
    assert rec.aliases == ["積算", "歩掛"]


def test_all_tags_returns_all(db, repo):
    db.store["rows"] = [
        (1, "A", None, None, []),
        (2, "B", None, None, []),
    ]
    repo.load()
    ids = sorted(t.id for t in repo.all_tags())
    assert ids == [1, 2]


def test_find_tags_by_alias_match_substring(db, repo):
    db.store["rows"] = [
        (3, "積算システム", None, None, ["積算", "歩掛"]),
        (12, "操作方法", None, 3, ["使い方"]),
        (20, "その他", None, None, []),
    ]
    repo.load()
    matched = repo.find_tags_by_alias_match("歩掛について教えてください")
    assert [m.id for m in matched] == [3]

    matched2 = repo.find_tags_by_alias_match("積算システムの使い方を教えて")
    # 「積算」も「使い方」も含むので両方一致
    assert sorted(m.id for m in matched2) == [3, 12]


def test_find_tags_by_alias_match_no_alias(db, repo):
    db.store["rows"] = [(20, "その他", None, None, [])]
    repo.load()
    assert repo.find_tags_by_alias_match("何か") == []


def test_find_tags_empty_query(db, repo):
    db.store["rows"] = [(3, "x", None, None, ["a"])]
    repo.load()
    assert repo.find_tags_by_alias_match("") == []


def test_reload_reflects_changes(db, repo):
    db.store["rows"] = [(1, "A", None, None, [])]
    repo.load()
    assert repo.tag_count() == 1
    # DB内容が変化した後 reload すると反映される
    db.store["rows"] = [
        (1, "A", None, None, []),
        (2, "B", None, None, ["b"]),
    ]
    repo.reload()
    assert repo.tag_count() == 2


def test_load_failure_keeps_existing_cache_and_raises(db, repo):
    db.store["rows"] = [(1, "A", None, None, [])]
    repo.load()
    assert repo.tag_count() == 1

    # 次の load は失敗させる → 例外を伝播しつつ、既存キャッシュは保持される
    db.store["fail"] = True
    with pytest.raises(RuntimeError):
        repo.reload()
    assert repo.tag_count() == 1
    assert repo.get(1).name == "A"
