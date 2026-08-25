"""db_hiroba_qa_init エントリポイント（IMPL-202608061016）。

処理順序:
  1. マイグレーション適用（yoyo-migrations, ADR-0017）。
  2. category の存在チェック→未投入なら投入。
  3. qa_original の存在チェック→未投入なら投入。
  4. question_altered の存在チェック→未投入なら、行ごとに embedding 計算のうえ投入。
  5. title 補完バックフィル（既存レコードの未設定行のみ対象。冪等）。
  6. tag.description / tag_alias の暫定シード（冪等）。

いずれかの手順で例外が発生した場合、ログに出力の上、非0の終了コードで終了する（ADR-0018）。
全手順が成功した場合は終了コード0で終了する。テーブル単位の存在チェックによる冪等性で、
再実行しても未投入分のみが投入される。
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2 import sql
from yoyo import get_backend, read_migrations

import backfill_title_and_tags
import seed_description_and_aliases
from db import DB
from embedding import get_embedding
from seed_helpers import (
    load_category_csv,
    load_qa_original_json,
    load_question_altered_csv,
)


DATABASE_URL = os.environ["DATABASE_URL"]
# conversation データベース（会話評価用, ADR-0044 / IMPL-202608241104 T15）。
# CONVERSATION_DB_NAME は存在チェック・CREATE DATABASE に使う（既定 "conversation"）。
# CONVERSATION_DB_URL は AWS 環境でのみ Terraform secrets 経由で注入される。ローカル
# docker-compose 環境では未設定のままとし、作成・スキーマ適用処理はスキップする（T19、10章）。
CONVERSATION_DB_NAME = os.environ.get("CONVERSATION_DB_NAME", "conversation")
CONVERSATION_DB_URL = os.environ.get("CONVERSATION_DB_URL", "")
# エクスポート専用読み取りロール（ADR-0046 / IMPL-202608241600 T1）。
# CHATBOT_DB_NAME は GRANT CONNECT ON DATABASE の対象名（既定 "chatbot"）。
# EXPORT_READER_ROLE_NAME は新設するロール名（既定 "chatbot_export_reader"）。
# EXPORT_READER_PASSWORD は AWS 環境でのみ Terraform secrets 経由で注入される。ローカル
# docker-compose 環境では未設定のままとし、ロール作成処理自体をスキップする（T3、10章）。
CHATBOT_DB_NAME = os.environ.get("CHATBOT_DB_NAME", "chatbot")
EXPORT_READER_ROLE_NAME = os.environ.get("EXPORT_READER_ROLE_NAME", "chatbot_export_reader")
EXPORT_READER_PASSWORD = os.environ.get("EXPORT_READER_PASSWORD", "")
# 埋め込み接続先の切り替え（IMPL-202608101616 4.3 / ADR-0031）。既定はローカル開発の lmstudio。
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "lmstudio")
if EMBEDDING_PROVIDER == "bedrock":
    EMBEDDING_URL = None
    EMBEDDING_MODEL = os.environ["BEDROCK_EMBEDDING_MODEL_ID"]
    BEDROCK_REGION = os.environ.get("BEDROCK_REGION")
else:
    EMBEDDING_URL = os.environ["LMSTUDIO_EMBEDDING_URL"]
    EMBEDDING_MODEL = os.environ["MODEL_EMBEDDING"]
    BEDROCK_REGION = None
# ADR-0034: シード元データはイメージに /data として同梱済み。CSV_DATA_DIR 未指定でも
# 同梱パスを既定で参照する（先頭に "/" を付けるため既定値 "data" → /data）。
CSV_DATA_DIR = "/" + os.environ.get("CSV_DATA_DIR", "data")
QA_ORIGINAL_FILE = os.environ["QA_ORIGINAL_FILE"]
QUESTION_ALTERED_FILE = os.environ["QUESTION_ALTERED_FILE"]
CATEGORY_FILE = os.environ["CATEGORY_FILE"]

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations"
)


def _now():
    return datetime.now(ZoneInfo("Asia/Tokyo"))


# ---------------------------------------------------------------------------
# 1. マイグレーション
# ---------------------------------------------------------------------------
def migrate():
    print(f"{_now()} ====== Applying migrations from {MIGRATIONS_DIR} ...")
    backend = get_backend(DATABASE_URL)
    migrations = read_migrations(MIGRATIONS_DIR)
    with backend.lock():
        to_apply = backend.to_apply(migrations)
        backend.apply_migrations(to_apply)
    print(f"{_now()} Migrations applied ({len(to_apply)} pending step(s)).")


# ---------------------------------------------------------------------------
# 1.5 conversation データベースの作成・スキーマ適用（ADR-0044 / IMPL-202608241104 T16, T17）
# ---------------------------------------------------------------------------
# db_conversation/init.sql と同一内容の冪等 DDL。yoyo の migrations/ には追加せず、
# chatbot データベースとは独立した conversation データベースへ直接適用する（0章 / T17）。
_CONVERSATION_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS conversation (
    id          VARCHAR PRIMARY KEY,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS message (
    id              VARCHAR PRIMARY KEY,
    conversation_id VARCHAR NOT NULL REFERENCES conversation(id),
    "order"         INTEGER NOT NULL,
    role            SMALLINT NOT NULL,
    evaluation      SMALLINT,
    input           TEXT,
    model           VARCHAR,
    content         TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(conversation_id, "order")
);
"""


def ensure_conversation_database():
    """conversation データベースが無ければ作成する（T16, ADR-0044）。

    CREATE DATABASE は PostgreSQL のトランザクションブロック内で実行できないため、
    既存の migrate()（yoyo が内部でトランザクションを張る）とは独立した接続・関数として、
    DATABASE_URL（chatbot データベース, マスター権限）に autocommit=True で接続して実行する（0章）。
    """
    print(f"{_now()} ====== Ensuring conversation database '{CONVERSATION_DB_NAME}' ...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True  # CREATE DATABASE はトランザクション不可（0章 / 10章）
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (CONVERSATION_DB_NAME,),
            )
            if cur.fetchone():
                print(
                    f"{_now()} Database '{CONVERSATION_DB_NAME}' already exists. "
                    "Skipping creation."
                )
                return
            cur.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(CONVERSATION_DB_NAME)
                )
            )
        print(f"{_now()} Database '{CONVERSATION_DB_NAME}' created.")
    finally:
        conn.close()


def apply_conversation_schema():
    """conversation データベースへ conversation/message テーブルの冪等 DDL を適用する（T17）。

    CONVERSATION_DB_URL に接続し、CREATE TABLE IF NOT EXISTS を実行する。
    """
    print(f"{_now()} ====== Applying conversation schema (conversation/message) ...")
    conn = psycopg2.connect(CONVERSATION_DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(_CONVERSATION_SCHEMA_DDL)
        conn.commit()
    finally:
        conn.close()
    print(f"{_now()} Conversation schema applied.")


# ---------------------------------------------------------------------------
# 1.6 エクスポート専用読み取りロールの作成（ADR-0046 / IMPL-202608241600 T2）
# ---------------------------------------------------------------------------
def ensure_export_reader_role():
    """chatbot データベース向けの読み取り専用ロールを冪等に作成・権限付与する（T2, ADR-0046）。

    admin_ui のエクスポート機能が使う専用ロール。DATABASE_URL（chatbot データベース,
    マスター権限）に接続し、次を冪等に行う:
      - ロールが無ければ CREATE ROLE ... WITH LOGIN PASSWORD、あれば ALTER ROLE ... PASSWORD
        （Terraform でパスワードを再生成した場合に追従する）
      - GRANT CONNECT / USAGE / SELECT（対象は既存テーブルのみ。呼び出しは migrate()・
        seed_if_empty() の後、全テーブル作成済みを保証してから行う, 0章 / 10章）
      - ALTER DEFAULT PRIVILEGES で将来追加テーブルにも SELECT を既定付与
      - REVOKE CONNECT ON DATABASE conversation（会話データベースへの接続は禁止）
    INSERT/UPDATE/DELETE・DDL 権限は一切付与しない（GRANT を追加しないだけでよい）。

    ロール名・データベース名は SQL インジェクション対策として sql.Identifier で組み立てる
    （既存 ensure_conversation_database() と同一パターン）。CREATE ROLE / GRANT は
    トランザクション内でも実行可能だが、既存パターンとの一貫性のため autocommit=True で処理する（10章）。
    """
    print(f"{_now()} ====== Ensuring export reader role '{EXPORT_READER_ROLE_NAME}' ...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True  # 既存 ensure_conversation_database() との一貫性（10章）
    try:
        role = sql.Identifier(EXPORT_READER_ROLE_NAME)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s",
                (EXPORT_READER_ROLE_NAME,),
            )
            if cur.fetchone():
                cur.execute(
                    sql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(role),
                    (EXPORT_READER_PASSWORD,),
                )
                print(f"{_now()} Role '{EXPORT_READER_ROLE_NAME}' already exists; password updated.")
            else:
                cur.execute(
                    sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD %s").format(role),
                    (EXPORT_READER_PASSWORD,),
                )
                print(f"{_now()} Role '{EXPORT_READER_ROLE_NAME}' created.")
            # 読み取り権限のみを付与する。
            cur.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(CHATBOT_DB_NAME), role
                )
            )
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
            cur.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(role)
            )
            cur.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT SELECT ON TABLES TO {}"
                ).format(role)
            )
            # conversation データベースへの接続を禁止する（5.1 節手順6）。GRANT/REVOKE ... ON DATABASE
            # はクラスタ共通カタログ（pg_database）への操作であり、chatbot 接続のまま発行してよい（10章）。
            # 注意: PostgreSQL は既定で PUBLIC に CONNECT を付与するため、ロール宛の REVOKE のみでは
            # PUBLIC 経由の接続は残る。DoD 8.1（conversation への接続自体を拒否）を厳密に満たすには
            # PUBLIC からの REVOKE も要る。ここでは指示書 5.1 の記載どおりロール宛 REVOKE のみを行う
            # （SELECT 権限は付与しないため、接続できてもテーブルは読めない）。
            cur.execute(
                sql.SQL("REVOKE CONNECT ON DATABASE {} FROM {}").format(
                    sql.Identifier(CONVERSATION_DB_NAME), role
                )
            )
        print(f"{_now()} Export reader role ensured (SELECT-only).")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2-4. シード（テーブル単位の存在チェックによる冪等投入, ADR-0018）
# ---------------------------------------------------------------------------
def seed_category():
    print(f"{_now()} ====== Start seeding category...")
    rows = load_category_csv(CSV_DATA_DIR, CATEGORY_FILE)
    with DB(DATABASE_URL) as db:
        if db.exists_category():
            print(f"{_now()} category table already has data. Skipping insertion.")
            return
        if rows:
            db.insert_category(rows)
    print(f"{_now()} Inserted {len(rows)} categories.")


def seed_qa_original():
    print(f"{_now()} ====== Start seeding qa_original...")
    rows = load_qa_original_json(CSV_DATA_DIR, QA_ORIGINAL_FILE, CATEGORY_FILE)
    with DB(DATABASE_URL) as db:
        if db.exists_qa_original():
            print(f"{_now()} qa_original table already has data. Skipping insertion.")
            return
        if rows:
            db.insert_qa_original(rows)
    print(f"{_now()} Inserted {len(rows)} qa_original rows.")


def seed_question_altered():
    print(f"{_now()} ====== Start seeding question_altered...")
    rows = load_question_altered_csv(CSV_DATA_DIR, QUESTION_ALTERED_FILE)
    with DB(DATABASE_URL) as db:
        if db.exists_question_altered():
            print(
                f"{_now()} question_altered table already has data. Skipping insertion."
            )
            return
        for row in rows:
            if row.embedding is None:
                row.embedding = get_embedding(
                    EMBEDDING_PROVIDER,
                    EMBEDDING_URL,
                    EMBEDDING_MODEL,
                    row.text,
                    BEDROCK_REGION,
                )
        if rows:
            db.insert_question_altered(rows)
    print(f"{_now()} Inserted {len(rows)} question_altered rows.")


# ---------------------------------------------------------------------------
# 5-6. バックフィル / 暫定シード（既存レコードへの冪等な補完）
# ---------------------------------------------------------------------------
def backfill_titles_and_tags():
    print(f"{_now()} ====== Start backfilling title / tags...")
    json_path = os.path.join(CSV_DATA_DIR, QA_ORIGINAL_FILE)
    items = backfill_title_and_tags.load_records(json_path)
    conn = psycopg2.connect(DATABASE_URL)
    try:
        stats = backfill_title_and_tags.backfill(conn, items)
    finally:
        conn.close()
    print(
        f"{_now()} backfill done: "
        f"titles updated={stats['updated_titles']}, "
        f"unique tags={stats['unique_tags']}, "
        f"qa_tag links={stats['qa_tag_links']}"
    )


def seed_tag_descriptions_and_aliases():
    print(f"{_now()} ====== Start seeding tag description / aliases (provisional)...")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        stats = seed_description_and_aliases.seed(conn)
    finally:
        conn.close()
    print(
        f"{_now()} tag description/alias seed done: "
        f"descriptions updated={stats['updated_descriptions']}, "
        f"aliases inserted={stats['inserted_aliases']}, "
        f"skipped missing tags={stats['skipped_missing_tags']}"
    )


def seed_if_empty():
    seed_category()
    seed_qa_original()
    seed_question_altered()
    backfill_titles_and_tags()
    seed_tag_descriptions_and_aliases()


def main():
    print(f"{_now()} ====== db_hiroba_qa_init start.")
    try:
        migrate()
        # conversation データベースの作成・スキーマ適用（AWS 環境のみ, T18/T19）。
        # ローカル docker-compose では別コンテナ（conversation_db）が既に conversation
        # データベースを保持しているため、CONVERSATION_DB_URL 未設定時は本ステップをスキップする。
        if CONVERSATION_DB_URL:
            ensure_conversation_database()
            apply_conversation_schema()
        else:
            print(
                f"{_now()} CONVERSATION_DB_URL is not set; "
                "skipping conversation database setup (local docker-compose)."
            )
        seed_if_empty()
        # エクスポート専用読み取りロールの作成（AWS 環境のみ, T3 / ADR-0046）。
        # GRANT SELECT ON ALL TABLES は実行時点で存在するテーブルにのみ効くため、必ず
        # migrate()・seed_if_empty() の後に呼ぶ（0章 / 10章）。ローカル docker-compose では
        # EXPORT_READER_PASSWORD 未設定のためスキップし、config.py が既存 DATABASE_URL に
        # フォールバックする。
        if EXPORT_READER_PASSWORD:
            ensure_export_reader_role()
        else:
            print(
                f"{_now()} EXPORT_READER_PASSWORD is not set; "
                "skipping export reader role setup (local docker-compose)."
            )
    except Exception as exc:  # noqa: BLE001 - ワンショット処理として全例外を捕捉し非0終了する
        print(f"{_now()} ERROR: db_hiroba_qa_init failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    print(f"{_now()} ====== db_hiroba_qa_init completed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
