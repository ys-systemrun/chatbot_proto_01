"""CSV スナップショットの取り込み（ADR-0109 段階 2）の純関数の単体テスト。

DB には触れない。取り込みの全体（全消去→COPY→照合→埋め込み補完→記録）と、退避 SQL から戻した DB との
完全一致・照合で止まること・シーケンスの調整は、pgvector のコンテナで実データを使って確認した。
"""

import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import import_data
import snapshot_export
import snapshot_import


def _entry(label, files):
    hashes = {t: hashlib.sha256(d).hexdigest() for t, d in files.items()}
    return {
        "tables": {t: {"file": f"{t}.csv", "sha256": h, "columns": ["id"]} for t, h in hashes.items()},
        "snapshot_sha256": snapshot_export.snapshot_sha256(hashes),
        "schema_version": ["0001"],
    }


def _files(label):
    return {t: f'id\n"{i}"\n'.encode("utf-8") for i, t in enumerate(import_data.tables_for(label))}


def test_verify_files_accepts_consistent_snapshot():
    files = _files("conversation")
    snapshot_import.verify_files("conversation", _entry("conversation", files), files)


def test_verify_files_rejects_tampered_csv_and_wrong_table_set():
    files = _files("conversation")
    entry = _entry("conversation", files)
    tampered = dict(files, message=b'id\n"999"\n')
    with pytest.raises(RuntimeError, match="SHA-256"):
        snapshot_import.verify_files("conversation", entry, tampered)
    entry_missing = dict(entry, tables={k: v for k, v in entry["tables"].items() if k != "release"})
    with pytest.raises(RuntimeError, match="テーブル構成"):
        snapshot_import.verify_files("conversation", entry_missing, files)


def test_csv_header():
    assert snapshot_import.csv_header(b'id,name,"a,b"\n"1","x","y"\n') == ["id", "name", "a,b"]


def test_schema_problem():
    assert snapshot_import.schema_problem(["0001", "0002"], ["0001", "0002"]) is None
    assert "スキーマ版" in snapshot_import.schema_problem(["0001"], ["0001", "0002"])


def test_drift_problem():
    assert snapshot_import.drift_problem(False, None, None) is None  # 空の DB はいつでも取り込める
    assert snapshot_import.drift_problem(True, "a", "a") is None  # 記録した版のまま
    assert "変わっています" in snapshot_import.drift_problem(True, "b", "a")
    assert "記録がありません" in snapshot_import.drift_problem(True, "a", None)


def test_embedding_cache_dir_and_loading(tmp_path):
    assert snapshot_import.cache_dir_name("amazon.titan-embed-text-v2:0") == "amazon.titan-embed-text-v2_0"
    assert snapshot_import.load_embedding_cache(str(tmp_path), "m:1") is None
    d = tmp_path / "m_1"
    d.mkdir()
    key = snapshot_import.text_key("こんにちは")
    (d / "embeddings.csv").write_text(f'"text_sha256","embedding"\n"{key}","[0.1,0.2]"\n', encoding="utf-8")
    assert snapshot_import.load_embedding_cache(str(tmp_path), "m:1") == {key: "[0.1,0.2]"}
