"""IMPL-202608061016 / 統合マイグレーション 0002（Pythonステップ）。

question_altered テーブルを作成する。embedding の次元数（VECTOR(N)）は使用する
embedding モデルに依存する（db_nomic: 768, db_multilingual: 384）ため、環境変数
EMBEDDING_VECTOR_DIM を読み込み VECTOR(N) を組み立てる（ADR-0017）。

is_primary 列は後続の 0004 で追加する（既存の手動マイグレーション順序に合わせる）。
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
            CREATE TABLE IF NOT EXISTS question_altered (
                id SERIAL PRIMARY KEY,
                qa_id TEXT,
                text TEXT,
                embedding VECTOR({dim})
            )
            """
        )


steps = [step(_apply)]
