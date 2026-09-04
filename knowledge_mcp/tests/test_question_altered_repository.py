"""QuestionAlteredRepository の単体テスト（IMPL-202608281100 T8 / ADR-0064）。

DB非依存のため、FakeDatabase が SQL/パラメータを記録し、テストが仕込んだ行を返す。
書き込み系（create/update/delete/import）が is_primary=false を不変条件として守ること、
is_primary=true 行・不存在・qa_id 付け替えを拒否することを確認する。
"""

import os
import sys
from contextlib import contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from knowledge_mcp.models.question_altered import QuestionAlteredError  # noqa: E402
from knowledge_mcp.repository.question_altered_repository import (  # noqa: E402
    QuestionAlteredRepository,
)


class FakeCursor:
    def __init__(self, responder, log):
        self._responder = responder
        self._log = log
        self._last = None

    def execute(self, sql, params=None):
        self._log.append({"sql": sql, "params": params})
        # responder(sql, params) -> このexecuteに対する fetchone/fetchall の戻り値
        self._last = self._responder(sql, params)

    def fetchone(self):
        return self._last

    def fetchall(self):
        return self._last or []


class FakeDatabase:
    """responder: (sql, params) -> fetchone/fetchall が返す値を決める関数。"""

    def __init__(self, responder=None):
        self._responder = responder or (lambda sql, params: None)
        self.log = []

    @contextmanager
    def cursor(self):
        yield FakeCursor(self._responder, self.log)


def _embed(_text):
    return [0.1, 0.2, 0.3]


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #
def test_list_filters_is_primary_false_only():
    def responder(sql, params):
        if sql.strip().startswith("SELECT COUNT"):
            return (0,)
        return []

    db = FakeDatabase(responder)
    repo = QuestionAlteredRepository(db, _embed)
    items, total = repo.list_question_altered()

    assert total == 0
    assert items == []
    # count と list の両方に is_primary = false 条件が入る
    assert all("qa.is_primary = false" in e["sql"] for e in db.log)


def test_list_adds_qa_id_and_keyword_conditions():
    def responder(sql, params):
        return (0,) if "COUNT" in sql else []

    db = FakeDatabase(responder)
    repo = QuestionAlteredRepository(db, _embed)
    repo.list_question_altered(qa_id="qa-1", keyword="パスワード", limit=5, offset=10)

    list_entry = db.log[-1]
    assert "qa.qa_id = %s" in list_entry["sql"]
    assert "qa.text ILIKE %s" in list_entry["sql"]
    # params: [qa_id, keyword, limit, offset]
    assert list_entry["params"] == ["qa-1", "%パスワード%", 5, 10]


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
def test_create_embeds_and_inserts_is_primary_false():
    calls = {"embedded": []}

    def embed(text):
        calls["embedded"].append(text)
        return [0.5, 0.6]

    def responder(sql, params):
        if sql.strip().startswith("SELECT 1 FROM hiroba_qa_original"):
            return (1,)  # qa_id 存在
        if "RETURNING id" in sql:
            return (42,)  # INSERT ... RETURNING id
        if "FROM hiroba_question_altered qa" in sql:  # _load
            return (42, "qa-1", "タイトル", "本文", False)
        return None

    db = FakeDatabase(responder)
    repo = QuestionAlteredRepository(db, embed)
    model = repo.create_question_altered("qa-1", "本文")

    assert model.id == 42
    assert model.is_primary is False
    assert calls["embedded"] == ["本文"]
    insert = next(e for e in db.log if "INSERT INTO hiroba_question_altered" in e["sql"])
    assert "false" in insert["sql"]  # is_primary=false 固定


def test_create_requires_qa_id_and_text():
    repo = QuestionAlteredRepository(FakeDatabase(), _embed)
    try:
        repo.create_question_altered("", "本文")
        assert False, "expected QuestionAlteredError"
    except QuestionAlteredError:
        pass


def test_create_rejects_missing_qa():
    def responder(sql, params):
        if sql.strip().startswith("SELECT 1 FROM hiroba_qa_original"):
            return None  # qa_id 不存在
        return None

    repo = QuestionAlteredRepository(FakeDatabase(responder), _embed)
    try:
        repo.create_question_altered("missing", "本文")
        assert False, "expected QuestionAlteredError"
    except QuestionAlteredError as e:
        assert "qa id=missing" in str(e)


# --------------------------------------------------------------------------- #
# update / delete
# --------------------------------------------------------------------------- #
def test_update_rejects_primary_row():
    def responder(sql, params):
        if "FROM hiroba_question_altered qa" in sql:
            return (7, "qa-1", "タイトル", "本文", True)  # is_primary=true
        return None

    repo = QuestionAlteredRepository(FakeDatabase(responder), _embed)
    try:
        repo.update_question_altered(7, "新本文")
        assert False, "expected QuestionAlteredError"
    except QuestionAlteredError as e:
        assert "primary" in str(e)


def test_update_rejects_missing_row():
    repo = QuestionAlteredRepository(FakeDatabase(lambda s, p: None), _embed)
    try:
        repo.update_question_altered(99, "新本文")
        assert False, "expected QuestionAlteredError"
    except QuestionAlteredError as e:
        assert "does not exist" in str(e)


def test_delete_rejects_primary_row():
    def responder(sql, params):
        if "FROM hiroba_question_altered qa" in sql:
            return (7, "qa-1", "タイトル", "本文", True)
        return None

    repo = QuestionAlteredRepository(FakeDatabase(responder), _embed)
    try:
        repo.delete_question_altered(7)
        assert False, "expected QuestionAlteredError"
    except QuestionAlteredError as e:
        assert "primary" in str(e)


# --------------------------------------------------------------------------- #
# import batch
# --------------------------------------------------------------------------- #
def test_import_batch_create_and_update_and_errors():
    # id 空=create（qa存在）、id=7 は primary でエラー、id=5 は qa_id 付け替えでエラー
    def responder(sql, params):
        if sql.strip().startswith("SELECT 1 FROM hiroba_qa_original"):
            return (1,)
        if "RETURNING id" in sql:
            return (100,)
        if "FROM hiroba_question_altered qa" in sql:
            item_id = params[0]
            if item_id == 7:
                return (7, "qa-x", "T", "既存", True)   # primary
            if item_id == 5:
                return (5, "qa-orig", "T", "既存", False)  # 付け替え検出用
            return (item_id, "qa-orig", "T", "既存", False)
        return None

    db = FakeDatabase(responder)
    repo = QuestionAlteredRepository(db, _embed)
    rows = [
        {"id": "", "qa_id": "qa-1", "text": "新規"},          # create -> success
        {"id": "7", "qa_id": "", "text": "更新"},             # primary -> error
        {"id": "5", "qa_id": "qa-other", "text": "更新"},     # reassign -> error
        {"id": "9", "qa_id": "qa-orig", "text": "更新"},      # same qa_id -> success
    ]
    results = repo.import_question_altered_batch(rows)

    assert results[0]["status"] == "success" and results[0]["id"] == 100
    assert results[1]["status"] == "error" and "primary" in results[1]["error"]
    assert results[2]["status"] == "error" and "reassignment" in results[2]["error"]
    assert results[3]["status"] == "success"


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def test_export_returns_is_primary_false_rows():
    def responder(sql, params):
        return [
            (1, "qa-1", "言い換えA", False),
            (2, "qa-2", "言い換えB", False),
        ]

    db = FakeDatabase(responder)
    repo = QuestionAlteredRepository(db, _embed)
    items = repo.export_question_altered()

    assert items == [
        {"id": 1, "qa_id": "qa-1", "text": "言い換えA", "is_primary": False},
        {"id": 2, "qa_id": "qa-2", "text": "言い換えB", "is_primary": False},
    ]
    assert "WHERE is_primary = false" in db.log[0]["sql"]
