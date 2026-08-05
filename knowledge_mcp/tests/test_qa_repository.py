"""QARepository の単体テスト（実装指示書 9.1）。

- スコア変換式の境界値（distance=0, distance大）。
- tags/category フィルタ有無によるSQL条件・パラメータの差分。
- 取得行から Document への変換（metadata に tags/category/guid が入ること）。

DB非依存のため、FakeDatabase がSQL/パラメータを記録し、固定行を返す。
"""

import os
import sys
from contextlib import contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from knowledge_mcp.repository.qa_repository import QARepository, distance_to_score


class FakeCursor:
    def __init__(self, rows, log):
        self._rows = rows
        self._log = log

    def execute(self, sql, params=None):
        self._log.append({"sql": sql, "params": params})

    def fetchall(self):
        return self._rows


class FakeDatabase:
    def __init__(self, rows):
        self._rows = rows
        self.log = []

    @contextmanager
    def cursor(self):
        yield FakeCursor(self._rows, self.log)


def _embed(_text):
    return [0.1, 0.2, 0.3]


def test_distance_to_score_boundaries():
    assert distance_to_score(0.0) == 1.0          # 最も類似
    assert distance_to_score(1.0) == 0.5
    assert 0.0 < distance_to_score(1000.0) < 0.01  # distance大 -> 0 に近づく


def test_row_maps_to_document_with_metadata():
    row = (
        "guid-1",                      # qa_id
        "タイトル",                     # title
        "回答本文",                     # answer
        "元の質問",                     # question_original
        "言い換え質問",                  # question (altered)
        "カテゴリA",                    # category_name
        ["tagX", "tagY"],              # tags
        0.0,                           # distance
    )
    db = FakeDatabase([row])
    repo = QARepository(db, _embed)

    docs = repo.search("q")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.id == "guid-1"
    assert doc.source_type == "qa"
    assert doc.title == "タイトル"
    assert doc.content == "回答本文"
    assert doc.score == 1.0
    assert doc.metadata == {
        "tags": ["tagX", "tagY"],
        "category": "カテゴリA",
        "guid": "guid-1",
    }


def test_no_filters_produces_no_where_conditions():
    db = FakeDatabase([])
    repo = QARepository(db, _embed)
    repo.search("q", top_k=5)

    sql = db.log[0]["sql"]
    # フィルタ条件（category / tags）が付かないこと
    assert "category_id = (SELECT id FROM category WHERE name = %s)" not in sql
    assert "= ANY(%s)" not in sql
    # params: SELECT<=> vec, ORDER BY<=> vec, LIMIT のみ
    assert db.log[0]["params"][-1] == 5
    assert len(db.log[0]["params"]) == 3


def test_category_filter_adds_condition_and_param():
    db = FakeDatabase([])
    repo = QARepository(db, _embed)
    repo.search("q", category="カテゴリA", top_k=3)

    entry = db.log[0]
    assert "category_id = (SELECT id FROM category WHERE name = %s)" in entry["sql"]
    assert "カテゴリA" in entry["params"]


def test_tags_filter_adds_all_match_condition():
    db = FakeDatabase([])
    repo = QARepository(db, _embed)
    repo.search("q", tags=["t1", "t2"], top_k=3)

    entry = db.log[0]
    assert "= ANY(%s)" in entry["sql"]
    # 指定タグ数（重複除外）が完全一致条件の右辺に渡る
    assert ["t1", "t2"] in entry["params"]
    assert 2 in entry["params"]
