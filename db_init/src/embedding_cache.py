"""埋め込みキャッシュ（ADR-0109 §5）。

スナップショットは埋め込み（vector 列）を含めないため、取り込みのたびに計算し直さずに済むよう、
「埋め込みモデル ID × 埋め込み元テキストの SHA-256 → ベクトル」を別に持つ。

置き場所: <cache_root>/<モデル ID をディレクトリ名にしたもの>/embeddings.csv と meta.json
（イメージでは /data/embedding_cache/、リポジトリでは db_init/data/embedding_cache/, DVC 管理）。
embeddings.csv は列 text_sha256,embedding（pgvector の text 表現）。キーの順に並べる（差分を読めるようにする）。

埋め込み元テキストはシードと同じ: 言い換え質問文は text、トラブルシューティング記事は
troubleshooting_import.build_embedding_text（title + subtitle + symptom + cause + guidance）。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os

import troubleshooting_import

EMBEDDINGS_FILE = "embeddings.csv"
META_FILE = "meta.json"


def dir_name(model_id: str) -> str:
    """モデル ID をディレクトリ名にする（Windows で使えない ':' などを '_' に）。"""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in model_id)


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def article_text(title, subtitle, symptom, cause, guidance) -> str:
    article = troubleshooting_import.TroubleshootingArticle(
        source_key="", title=title, body_html="", guidance=guidance or "",
        subtitle=subtitle, symptom=symptom, cause=cause,
    )
    return troubleshooting_import.build_embedding_text(article)


def dimensions(vector_text: str) -> int:
    return len(vector_text.strip("[]").split(","))


def load(cache_root: str, model_id: str) -> "dict[str, str] | None":
    """{テキストの SHA-256: pgvector 形式のベクトル}。キャッシュが無ければ None。"""
    path = os.path.join(cache_root, dir_name(model_id), EMBEDDINGS_FILE)
    if not os.path.exists(path):
        return None
    csv.field_size_limit(1 << 30)
    with open(path, encoding="utf-8", newline="") as f:
        return {row["text_sha256"]: row["embedding"] for row in csv.DictReader(f)}


def collect_from_db(cur) -> dict[str, str]:
    """knowledge DB にある埋め込みを {テキストの SHA-256: ベクトル} にする。"""
    entries: dict[str, str] = {}
    cur.execute("SELECT text, embedding::text FROM hiroba_question_altered WHERE embedding IS NOT NULL AND text IS NOT NULL")
    for text, vector in cur.fetchall():
        entries[text_key(text)] = vector
    cur.execute(
        "SELECT title, subtitle, symptom, cause, guidance, embedding::text FROM troubleshooting_article "
        "WHERE embedding IS NOT NULL"
    )
    for title, subtitle, symptom, cause, guidance, vector in cur.fetchall():
        entries[text_key(article_text(title, subtitle, symptom, cause, guidance))] = vector
    return entries


def merge(existing: "dict[str, str] | None", from_db: dict[str, str]) -> "tuple[dict[str, str], int]":
    """既存のキャッシュに DB の埋め込みを足す（同じキーは DB を優先）。(結果, 新しく増えた件数) を返す。

    DB から消えたテキストのベクトルも残す（同じ文が戻ったときに計算し直さずに済む）。
    """
    merged = dict(existing or {})
    added = sum(1 for k in from_db if k not in merged)
    merged.update(from_db)
    return merged, added


def render(entries: dict[str, str]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(["text_sha256", "embedding"])
    for key in sorted(entries):
        writer.writerow([key, entries[key]])
    return buf.getvalue().encode("utf-8")


def render_meta(model_id: str, entries: dict[str, str], *, source: str) -> bytes:
    any_vector = next(iter(entries.values()), None)
    meta = {
        "adr": "ADR-0109",
        "model_id": model_id,
        "dimensions": dimensions(any_vector) if any_vector else None,
        "entries": len(entries),
        "key": "SHA-256 of the embedding source text (UTF-8)",
        "source_text": "hiroba_question_altered.text / troubleshooting_import.build_embedding_text(article)",
        "source": source,
    }
    return json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")
