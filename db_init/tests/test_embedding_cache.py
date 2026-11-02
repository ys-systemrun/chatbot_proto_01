"""埋め込みキャッシュ（ADR-0109 段階 3）と、スナップショットのマニフェストの分割の単体テスト。

DB には触れない。書き出し時のキャッシュ更新（DB の埋め込みを足す）と、更新したキャッシュで取り込むと
埋め込みの計算が 0 件になることは、pgvector のコンテナとダミーの埋め込みサーバーで確認した。
"""

import csv
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import embedding_cache
import snapshot_export


def test_dir_name_and_text_key():
    assert embedding_cache.dir_name("amazon.titan-embed-text-v2:0") == "amazon.titan-embed-text-v2_0"
    assert embedding_cache.text_key("あ") == embedding_cache.text_key("あ") != embedding_cache.text_key("い")


def test_merge_keeps_old_entries_and_prefers_db():
    merged, added = embedding_cache.merge({"a": "[1]", "b": "[2]"}, {"b": "[9]", "c": "[3]"})
    assert merged == {"a": "[1]", "b": "[9]", "c": "[3]"}  # DB から消えた a も残す、b は DB を優先
    assert added == 1
    assert embedding_cache.merge(None, {"x": "[0]"}) == ({"x": "[0]"}, 1)


def test_render_is_sorted_and_loadable(tmp_path):
    data = embedding_cache.render({"bb": "[0.2,0.3]", "aa": "[0.1,0.4]"})
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
    assert rows == [["text_sha256", "embedding"], ["aa", "[0.1,0.4]"], ["bb", "[0.2,0.3]"]]
    d = tmp_path / embedding_cache.dir_name("m:1")
    d.mkdir()
    (d / embedding_cache.EMBEDDINGS_FILE).write_bytes(data)
    assert embedding_cache.load(str(tmp_path), "m:1") == {"aa": "[0.1,0.4]", "bb": "[0.2,0.3]"}
    assert embedding_cache.load(str(tmp_path), "other") is None


def test_render_meta():
    meta = json.loads(embedding_cache.render_meta("m:1", {"a": "[0.1,0.2,0.3]"}, source="s"))
    assert meta["model_id"] == "m:1" and meta["dimensions"] == 3 and meta["entries"] == 1


def test_article_text_matches_seed_embedding_text():
    text = embedding_cache.article_text("タイトル", None, "現象", None, "案内")
    assert text == "タイトル\n現象\n案内"


def test_split_manifest_puts_cache_on_knowledge_only():
    manifest = {
        "format": 2, "created_at": "c",
        "databases": {"knowledge": {"k": 1}, "conversation": {"c": 1}},
        "embedding_cache": {"model_id": "m"},
    }
    parts = snapshot_export.split_manifest(manifest)
    assert parts["knowledge"]["databases"] == {"knowledge": {"k": 1}}
    assert parts["knowledge"]["embedding_cache"] == {"model_id": "m"}
    assert "embedding_cache" not in parts["conversation"]
    assert parts["conversation"]["created_at"] == "c"
