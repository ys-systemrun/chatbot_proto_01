"""CSV / SQL ダンプ生成ロジック（IMPL-202608241600 T16、5.5 節、ADR-0047）。

pg_dump / psql は使わず、既存依存の psycopg2 でテーブルを読み取り、アプリケーションコードで
CSV / SQL を組み立てる（0章 / ADR-0047）。テーブル名・カラム名は psycopg2.sql.Identifier で
組み立て、SQL の値エスケープは cur.mogrify を使う（手組みの文字列結合を避ける、5.5 節）。
"""

from __future__ import annotations

import io
import re

from psycopg2 import sql

from .tables import TableSpec

# INSERT のバッチサイズ（1 文あたりの行数。5.5 節 / Open Issue #4、目安 500 行）。
INSERT_BATCH_SIZE = 500


def detect_vector_dim(conn, table: str, column: str) -> int | None:
    """VECTOR 列の次元を実データベースから検出する（question_altered.embedding 用）。

    pgvector の VECTOR(N) は format_type で "vector(N)" として得られる。DDL の次元を環境に
    追従させ、SQL ダンプを別環境の空 DB へ再投入できるようにする（DoD 8.4）。
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = %s
              AND a.attname = %s
              AND a.attnum > 0
              AND NOT a.attisdropped
            """,
            (table, column),
        )
        row = cur.fetchone()
    if row and row[0]:
        m = re.search(r"\((\d+)\)", row[0])
        if m:
            return int(m.group(1))
    return None


def fetch_table_csv(conn, spec: TableSpec) -> bytes:
    """1テーブルを CSV（ヘッダ付き）バイト列として取得する。

    COPY (SELECT ... ORDER BY pk) TO STDOUT WITH CSV HEADER を copy_expert で実行する。
    """
    cols = sql.SQL(", ").join(sql.Identifier(c) for c in spec.csv_columns)
    order = sql.SQL(", ").join(sql.Identifier(c) for c in spec.order_by)
    copy_stmt = sql.SQL(
        "COPY (SELECT {cols} FROM {tbl} ORDER BY {order}) TO STDOUT WITH CSV HEADER"
    ).format(cols=cols, tbl=sql.Identifier(spec.name), order=order)

    buf = io.BytesIO()
    with conn.cursor() as cur:
        cur.copy_expert(copy_stmt.as_string(conn), buf)
    return buf.getvalue()


def fetch_table_sql(conn, spec: TableSpec, embedding_dim: int | None = None) -> str:
    """1テーブルを CREATE TABLE IF NOT EXISTS + バッチ INSERT の SQL テキストとして返す。

    値のエスケープは cur.mogrify に委ね、SQL インジェクションを避ける（5.5 節）。
    embedding（VECTOR 型）は psycopg2 が文字列（"[...]"）として返し、そのまま文字列リテラルとして
    INSERT すると pgvector の入力関数により VECTOR へ復元される（DoD 8.4）。
    """
    parts: list[str] = [spec.create_ddl(embedding_dim).rstrip() + "\n"]

    col_ident = sql.SQL(", ").join(sql.Identifier(c) for c in spec.columns)
    order_ident = sql.SQL(", ").join(sql.Identifier(c) for c in spec.order_by)
    select_stmt = sql.SQL("SELECT {cols} FROM {tbl} ORDER BY {order}").format(
        cols=col_ident, tbl=sql.Identifier(spec.name), order=order_ident
    )

    tbl_sql = sql.Identifier(spec.name).as_string(conn)
    col_sql = col_ident.as_string(conn)
    placeholder = "(" + ", ".join(["%s"] * len(spec.columns)) + ")"

    with conn.cursor() as cur:
        cur.execute(select_stmt)
        rows = cur.fetchall()
        for start in range(0, len(rows), INSERT_BATCH_SIZE):
            batch = rows[start : start + INSERT_BATCH_SIZE]
            values = ",\n".join(
                cur.mogrify(placeholder, row).decode("utf-8") for row in batch
            )
            parts.append(f"INSERT INTO {tbl_sql} ({col_sql}) VALUES\n{values};\n")

    return "\n".join(parts)
