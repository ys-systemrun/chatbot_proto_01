"""export_data（退避エクスポート, ADR-0103）の単体テスト。

DB / S3 には触れず、対象外テーブルの検出・マニフェスト組み立て・ハッシュ・読み取りトランザクションの
扱い（対象外テーブルがあれば SQL を作らずに失敗し、必ずロールバックする）を検証する。
"""

import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import export_data
import import_data


def test_unexpected_tables_ignores_targets_and_yoyo():
    existing = ["tag", "hiroba_qa_tag", "_yoyo_migration", "_yoyo_log", "_yoyo_version", "yoyo_lock", "new_table"]
    assert export_data.unexpected_tables(existing, ["tag", "hiroba_qa_tag"]) == ["new_table"]
    assert export_data.unexpected_tables(["tag", "_yoyo_migration"], ["tag"]) == []


def test_sha256_hex():
    assert export_data.sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_build_manifest_shape():
    m = export_data.build_manifest(
        created_at="2026-10-21T10:00:00+09:00",
        timestamp="20261021100000",
        manifest_only=False,
        databases={"knowledge": {"tables": {"tag": 1}, "schema_version": ["0001"]}},
    )
    assert m["format"] == export_data.MANIFEST_FORMAT
    assert m["adr"] == "ADR-0103"
    assert m["databases"]["knowledge"]["schema_version"] == ["0001"]


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        q = " ".join(str(query).split())
        if "information_schema.tables" in q:
            self._rows = [(t,) for t in self.conn.tables]
        elif q.startswith("SELECT COUNT(*)"):
            self._rows = [(7,)]
        elif "_yoyo_migration" in q:
            self._rows = [("0001_init",), ("0002_add",)]
        else:
            raise AssertionError(f"unexpected query: {q}")

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0]


class _FakeConn:
    def __init__(self, tables):
        self.tables = tables
        self.session = None
        self.rolled_back = False

    def set_session(self, **kwargs):
        self.session = kwargs

    def cursor(self):
        return _FakeCursor(self)

    def rollback(self):
        self.rolled_back = True


def test_export_database_manifest_only_reads_counts_and_schema():
    tables = import_data.tables_for("conversation") + ["_yoyo_migration"]
    conn = _FakeConn(tables)

    body, info = export_data.export_database(conn, "conversation", manifest_only=True)

    assert body is None
    assert conn.session["readonly"] is True and conn.session["autocommit"] is False
    assert info["schema_version"] == ["0001_init", "0002_add"]
    assert set(info["tables"]) == set(import_data.tables_for("conversation"))
    assert conn.rolled_back


def test_export_database_refuses_unexpected_table():
    conn = _FakeConn(import_data.tables_for("knowledge") + ["brand_new"])

    with pytest.raises(RuntimeError, match="brand_new"):
        export_data.export_database(conn, "knowledge")

    assert conn.rolled_back


def test_export_database_refuses_missing_target_table():
    conn = _FakeConn(import_data.tables_for("knowledge")[1:])

    with pytest.raises(RuntimeError, match="存在しません"):
        export_data.export_database(conn, "knowledge", manifest_only=True)
