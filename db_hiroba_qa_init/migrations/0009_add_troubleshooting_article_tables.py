"""統合マイグレーション 0009（ADR-0076 / REQ-202609071337）。

トラブルシューティング記事用のテーブルを新設する（維津美の広場QAデータと同一の実DB内）。
  - troubleshooting_article: 2つの静的HTML文書（trouble_shooting.html /
    trouble_shooting_netauth.html）由来の1トピック（<h2>単位）を表す。source_key 列で出自を
    区別し、単一テーブルに集約する（ADR-0076 決定2）。
  - troubleshooting_article_tag: 共有タグマスタ tag(id) との中間テーブル。hiroba_qa_tag と
    対称的な構造（ADR-0076 決定4）。タグマスタ自体は新設せず、ADR-0077 でリネームした
    共有マスタ tag をそのまま参照する。

embedding の次元数（VECTOR(N)）は hiroba_question_altered.embedding と同一に揃える必要があるため
（同一の埋め込みモデル・embed_fn を使い回す, ADR-0078 §36）、0002 と同様に環境変数
EMBEDDING_VECTOR_DIM を読み込んで VECTOR(N) を組み立てる（ADR-0017）。

一意性制約 UNIQUE (source_key, title) はインポート時の冪等判定キーとして用いる
（要件定義書10.2節）。カテゴリ（hiroba_category 相当）は新設しない（分類は共有タグのみ, ADR-0076 決定5）。

冪等（CREATE TABLE IF NOT EXISTS）なので再実行しても無害。
"""

from __future__ import annotations

import os

from yoyo import step


def _apply(conn):
    raw = os.environ.get("EMBEDDING_VECTOR_DIM", "").strip()
    if not raw:
        raise RuntimeError(
            "EMBEDDING_VECTOR_DIM is not set (or empty). "
            "Set it in .env to match DB_DIR (db_nomic -> 768, db_multilingual -> 384)."
        )
    dim = int(raw)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS troubleshooting_article (
                id SERIAL PRIMARY KEY,
                source_key TEXT NOT NULL,
                title TEXT NOT NULL,
                subtitle TEXT,
                symptom TEXT,
                operation_history TEXT,
                error_code TEXT,
                error_message TEXT,
                system_environment TEXT,
                hardware_environment TEXT,
                version_info TEXT,
                guidance TEXT NOT NULL,
                cause TEXT,
                notes TEXT,
                keyword_raw TEXT,
                body_html TEXT NOT NULL,
                source_updated_at TIMESTAMP,
                embedding VECTOR({dim}),
                created_at TIMESTAMP NOT NULL DEFAULT now(),
                updated_at TIMESTAMP NOT NULL DEFAULT now(),
                UNIQUE (source_key, title)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS troubleshooting_article_tag (
                article_id INTEGER NOT NULL REFERENCES troubleshooting_article(id),
                tag_id INTEGER NOT NULL REFERENCES tag(id),
                PRIMARY KEY (article_id, tag_id)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_troubleshooting_article_tag_tag_id "
            "ON troubleshooting_article_tag (tag_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_troubleshooting_article_source_key "
            "ON troubleshooting_article (source_key)"
        )


steps = [step(_apply)]
