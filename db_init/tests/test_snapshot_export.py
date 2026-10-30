"""CSV スナップショットの書き出し（ADR-0109 段階 1）の純関数の単体テスト。

DB には触れない。書き出しと取り込みの往復（全テーブルの CSV が一致すること）は、pgvector の
コンテナで実データ（AWS の退避 SQL）を使って確認する（段階 2 で自動テストにする）。
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import snapshot_export


def test_snapshot_sha256_depends_on_table_order_and_hashes():
    a = snapshot_export.snapshot_sha256({"t1": "aa", "t2": "bb"})
    expected = hashlib.sha256("t1 aa\nt2 bb\n".encode("utf-8")).hexdigest()
    assert a == expected  # terraform/deploy の _snapshot_sha256 と同じ計算
    assert a != snapshot_export.snapshot_sha256({"t2": "bb", "t1": "aa"})
    assert a != snapshot_export.snapshot_sha256({"t1": "aa", "t2": "bc"})


def test_build_manifest_marks_snapshot_format():
    m = snapshot_export.build_manifest(created_at="c", timestamp="ts", databases={"knowledge": {}})
    assert m["format"] == 2 and m["adr"] == "ADR-0109" and m["kind"] == "snapshot"
    assert m["databases"] == {"knowledge": {}}


def test_csv_file_name():
    assert snapshot_export.csv_file_name("hiroba_qa_tag") == "hiroba_qa_tag.csv"
