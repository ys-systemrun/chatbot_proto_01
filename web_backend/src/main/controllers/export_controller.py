"""全データエクスポート（GET /api/export）のレスポンス生成ロジック（IMPL-202608241600 T18/T20）。

既存の qa_controller / tag_controller と同様、薄い呼び出し層に留める。ダンプ生成の実体は
src/export/（tables / dump / zipper）に委譲し、ここでは DB 接続の開閉・形式ごとのファイル束ね・
ZIP 化・ファイル名生成・ログ記録のみを担う（3章 / 5.5 節）。
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg2

from src.export import dump, tables, zipper
from src.export.tables import CHATBOT_TABLES, CONVERSATION_TABLES
from src.log import log_export
from src.main import config


def _timestamp() -> str:
    """ファイル名のタイムスタンプ（Asia/Tokyo, YYYYMMDDHHmmss）。

    db_hiroba_qa_init のログ出力（_now, Asia/Tokyo）に合わせる（Open Issue #5）。
    """
    return datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d%H%M%S")


def _build_csv_files() -> dict[str, bytes]:
    """CSV 形式: 12テーブルそれぞれを "{table}.csv" として束ねる（embedding は除外, ADR-0066）。"""
    files: dict[str, bytes] = {}
    with closing(psycopg2.connect(config.CHATBOT_EXPORT_DB_URL)) as chatbot_conn:
        for spec in CHATBOT_TABLES:
            files[f"{spec.name}.csv"] = dump.fetch_table_csv(chatbot_conn, spec)
    with closing(psycopg2.connect(config.CONVERSATION_DB_URL)) as conv_conn:
        for spec in CONVERSATION_TABLES:
            files[f"{spec.name}.csv"] = dump.fetch_table_csv(conv_conn, spec)
    return files


def _build_sql_files() -> dict[str, bytes]:
    """SQL 形式: データベースごとに "chatbot.sql" / "conversation.sql" の2ファイルを束ねる。"""
    files: dict[str, bytes] = {}

    with closing(psycopg2.connect(config.CHATBOT_EXPORT_DB_URL)) as chatbot_conn:
        embedding_dim = dump.detect_vector_dim(
            chatbot_conn, "hiroba_question_altered", "embedding"
        )
        parts = [tables.CHATBOT_SQL_HEADER]
        for spec in CHATBOT_TABLES:
            parts.append(dump.fetch_table_sql(chatbot_conn, spec, embedding_dim))
        files["chatbot.sql"] = "\n".join(parts).encode("utf-8")

    with closing(psycopg2.connect(config.CONVERSATION_DB_URL)) as conv_conn:
        parts = []
        for spec in CONVERSATION_TABLES:
            parts.append(dump.fetch_table_sql(conv_conn, spec))
        files["conversation.sql"] = "\n".join(parts).encode("utf-8")

    return files


def build_export(format: str) -> tuple[bytes, str]:
    """format（"sql" / "csv"）に応じて ZIP バイト列と添付ファイル名を返す。

    ファイル名は chatbot_invitro_export_<YYYYMMDDHHmmss>_<format>.zip（6章）。
    """
    if format == "csv":
        files = _build_csv_files()
    else:  # "sql"（app.py の pattern バリデーションで sql/csv 以外は 422 済み）
        files = _build_sql_files()

    zip_bytes = zipper.build_zip(files)
    filename = f"chatbot_invitro_export_{_timestamp()}_{format}.zip"
    log_export(format, filename)
    return zip_bytes, filename
