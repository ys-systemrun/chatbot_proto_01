"""TroubleshootingRepository（検索）/ TroubleshootingManagementRepository（管理）の単体テスト
（ADR-0078 / ADR-0079）。

DB非依存のため FakeDatabase が SQL/パラメータを記録し固定行を返す。検索行のカラム順:
    (article_id, title, subtitle, guidance, source_key, tag_names, article_closure,
     input_closure, distance)
"""

import os
import sys
from contextlib import contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from knowledge_mcp.repository.troubleshooting_repository import (  # noqa: E402
    SOURCE_TYPE,
    TroubleshootingRepository,
)
from knowledge_mcp.repository.troubleshooting_management_repository import (  # noqa: E402
    TroubleshootingManagementRepository,
)
from knowledge_mcp.models.troubleshooting import TroubleshootingError  # noqa: E402


class FakeCursor:
    def __init__(self, rows, log, fetchmany=None):
        self._rows = rows
        self._log = log
        # 複数回 fetchall/fetchone するケース用に、呼び出しごとに順番の結果を返す。
        self._fetch_queue = list(fetchmany) if fetchmany is not None else None

    def execute(self, sql, params=None):
        self._log.append({"sql": sql, "params": params})

    def executemany(self, sql, seq):
        self._log.append({"sql": sql, "params": list(seq), "many": True})

    def fetchall(self):
        if self._fetch_queue is not None:
            return self._fetch_queue.pop(0) if self._fetch_queue else []
        return self._rows

    def fetchone(self):
        if self._fetch_queue is not None:
            batch = self._fetch_queue.pop(0) if self._fetch_queue else []
            return batch[0] if batch else None
        return self._rows[0] if self._rows else None


class FakeDatabase:
    def __init__(self, rows=None, fetchmany=None):
        self._rows = rows or []
        self._fetchmany = fetchmany
        self.log = []

    @contextmanager
    def cursor(self):
        yield FakeCursor(self._rows, self.log, self._fetchmany)


def _embed(_text):
    return [0.1, 0.2, 0.3]


# --------------------------------------------------------------------------- #
# TroubleshootingRepository（検索）
# --------------------------------------------------------------------------- #
def test_search_maps_row_to_document_no_tags():
    row = (
        7,                       # article_id
        "マスタ読み込みエラー",   # title
        None,                    # subtitle
        "案内本文",               # guidance
        "trouble_shooting",      # source_key
        ["tagX"],                # tag_names
        [1],                     # article_closure
        None,                    # input_closure（tags 未指定）
        0.0,                     # distance
    )
    db = FakeDatabase([row])
    repo = TroubleshootingRepository(db, _embed)

    docs = repo.search("エラー")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.id == "7"
    assert doc.source_type == SOURCE_TYPE == "troubleshooting"
    assert doc.title == "マスタ読み込みエラー"
    assert doc.content == "案内本文"
    assert doc.score == 1.0
    assert doc.metadata == {
        "tags": ["tagX"],
        "category": None,
        "source_key": "trouble_shooting",
        "subtitle": None,
    }


def test_search_returns_empty_when_category_specified():
    db = FakeDatabase([("1", "t", None, "g", "trouble_shooting", [], [], None, 0.0)])
    repo = TroubleshootingRepository(db, _embed)
    # カテゴリ指定は本情報源に該当なし → 空・DBアクセスも行わない。
    assert repo.search("q", category="なにか") == []
    assert db.log == []


def test_search_tag_similarity_scoring_and_sort_topk():
    rows = [
        # 近い距離だがタグ不一致
        (1, "A", None, "gA", "trouble_shooting", ["x"], [10], [99], 0.0),
        # 遠い距離だがタグ一致（jaccard 高）
        (2, "B", None, "gB", "trouble_shooting", ["y"], [99], [99], 3.0),
    ]
    db = FakeDatabase(rows)
    repo = TroubleshootingRepository(db, _embed, tag_similarity_weight=0.5)

    docs = repo.search("q", tags=["something"], top_k=1)

    assert len(docs) == 1
    # row2: embedding_score=1/4=0.25, tag_sim=jaccard({99},{99})=1 -> 0.5*0.25+0.5*1=0.625
    # row1: embedding_score=1.0, tag_sim=jaccard({99},{10})=0 -> 0.5*1+0=0.5
    assert docs[0].id == "2"
    assert docs[0].metadata["tag_similarity"] == 1.0
    assert docs[0].metadata["embedding_score"] == 0.25


# --------------------------------------------------------------------------- #
# TroubleshootingManagementRepository（管理）
# --------------------------------------------------------------------------- #
def _detail_row(article_id=5):
    # _load_detail の1本目 SELECT が返す19カラム。
    return (
        article_id, "trouble_shooting", "旧タイトル", "sub", "現象", None,
        None, None, None, None, None, "旧案内", "原因", None, None, "<h2>旧タイトル</h2>",
        None, None, None,
    )


def test_update_rejects_unknown_field():
    db = FakeDatabase(fetchmany=[[_detail_row()], []])
    repo = TroubleshootingManagementRepository(db, _embed)
    try:
        repo.update_article(5, fields={"nope": "x"})
        assert False, "should raise"
    except TroubleshootingError as e:
        assert "unknown fields" in str(e)


def test_update_rejects_empty_not_null_field():
    db = FakeDatabase(fetchmany=[[_detail_row()], []])
    repo = TroubleshootingManagementRepository(db, _embed)
    try:
        repo.update_article(5, fields={"guidance": "   "})
        assert False, "should raise"
    except TroubleshootingError as e:
        assert "guidance" in str(e)


def test_update_recomputes_embedding_when_source_field_changes():
    # fetch順: get(load_detail SELECT→tags), update(load_detail SELECT→tags), reload(SELECT→tags)
    detail = _detail_row()
    db = FakeDatabase(
        fetchmany=[
            [detail], [],        # 1回目 _load_detail（存在確認）
            [detail], [],        # reload _load_detail
        ]
    )
    repo = TroubleshootingManagementRepository(db, _embed)
    repo.update_article(5, fields={"guidance": "新しい案内"})

    update_sqls = [e for e in db.log if "UPDATE troubleshooting_article SET" in e["sql"]]
    assert len(update_sqls) == 1
    assert "embedding = %s" in update_sqls[0]["sql"]
    assert "updated_at = now()" in update_sqls[0]["sql"]


def test_update_replaces_tags():
    detail = _detail_row()
    db = FakeDatabase(
        fetchmany=[
            [detail], [],   # 存在確認 _load_detail
            [(1,)],         # _assert_tags_exist（tag 存在）
            [detail], [],   # reload
        ]
    )
    repo = TroubleshootingManagementRepository(db, _embed)
    repo.update_article(5, tag_ids=[1])

    deletes = [e for e in db.log if e["sql"].startswith("DELETE FROM troubleshooting_article_tag")]
    inserts = [e for e in db.log if "INSERT INTO troubleshooting_article_tag" in e["sql"]]
    assert len(deletes) == 1
    assert len(inserts) == 1
