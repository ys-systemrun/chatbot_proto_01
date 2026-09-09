"""import_data（全データインポート, ADR-0066）の純関数の単体テスト。

DB / S3 には触れず、対象テーブル解決・TRUNCATE 文組み立て・全消去+投入の
トランザクション制御（コミット／失敗時ロールバック）を検証する。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import import_data


def test_parse_targets():
    assert import_data.parse_targets("both") == ["chatbot", "conversation"]
    assert import_data.parse_targets("chatbot") == ["chatbot"]
    assert import_data.parse_targets("conversation") == ["conversation"]
    with pytest.raises(ValueError):
        import_data.parse_targets("nope")


def test_tables_for_covers_chatbot_tables():
    # ADR-0072/0077: tag_folder を追加（tag.folder_id の参照先のため tag より前）。
    # ADR-0076: troubleshooting_article / troubleshooting_article_tag を末尾に追加。
    assert import_data.tables_for("chatbot") == [
        "hiroba_category",
        "hiroba_qa_original",
        "tag_folder",
        "tag",
        "hiroba_question_altered",
        "tag_alias",
        "hiroba_qa_tag",
        "troubleshooting_article",
        "troubleshooting_article_tag",
    ]
    # ADR-0066: conversation は検証4テーブルを含む計6テーブル。
    assert import_data.tables_for("conversation") == [
        "conversation",
        "message",
        "verification_question",
        "verification_run",
        "verification_run_tag",
        "verification_run_source",
    ]


def test_truncate_statement_quotes_and_cascades():
    stmt = import_data._truncate_statement(["conversation", "message"])
    assert stmt == 'TRUNCATE "conversation", "message" RESTART IDENTITY CASCADE;'


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt, params=None):
        s = stmt if isinstance(stmt, str) else str(stmt)
        if self._conn.fail_on and self._conn.fail_on in s:
            raise RuntimeError("boom")
        self._conn.executed.append(s)

    def fetchall(self):
        # resync_sequences の introspection 結果。既定はシーケンス非依存（setval を発行しない）。
        return self._conn.seq_rows


class _FakeConn:
    def __init__(self, fail_on=None, seq_rows=None):
        self.executed = []
        self.committed = False
        self.rolled_back = False
        self.autocommit = True
        self.fail_on = fail_on
        self.seq_rows = seq_rows or []

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_truncate_and_apply_commits_in_one_transaction():
    conn = _FakeConn()
    import_data.truncate_and_apply(conn, ["conversation", "message"], "INSERT INTO x ...;")
    assert conn.autocommit is False
    assert conn.committed and not conn.rolled_back
    # TRUNCATE を先に、続けてダンプを適用する。
    assert conn.executed[0].startswith("TRUNCATE ")
    assert conn.executed[1] == "INSERT INTO x ...;"


def test_truncate_and_apply_rolls_back_on_failure():
    conn = _FakeConn(fail_on="INSERT")
    with pytest.raises(RuntimeError):
        import_data.truncate_and_apply(conn, ["message"], "INSERT INTO x ...;")
    assert conn.rolled_back and not conn.committed


def test_resync_sequences_setval_for_serial_columns():
    # tag.id はシーケンス依存、name は非依存として introspection 結果を返す。
    conn = _FakeConn(seq_rows=[("id", "public.tag_id_seq"), ("name", None)])
    with conn.cursor() as cur:
        import_data.resync_sequences(cur, ["tag"])
    # setval を含む文が発行され（id 列のみ）、name 列には発行されない。
    setvals = [s for s in conn.executed if "setval" in s]
    assert len(setvals) == 1
    assert "MAX" in setvals[0]
