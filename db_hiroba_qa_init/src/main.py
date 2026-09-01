"""db_hiroba_qa_init エントリポイント（IMPL-202608061016、IMPL-202608261022 で拡張）。

処理順序:
  1. chatbot ロール分離: migrator / app ロールを作成（マスター接続, ADR-0052）。
  2. chatbot マイグレーション適用（yoyo, migrator 接続, ADR-0017）。
  3. chatbot シード（category / qa_original / question_altered / backfill / tag 説明, migrator 接続）。
  4. chatbot app ロールへ DML 権限を付与（全テーブル作成後, マスター接続）。
  5. conversation データベースの作成（AWS のみ）→ ロール作成 → yoyo マイグレーション → app 権限付与。
  6. エクスポート専用読み取りロールの作成（AWS のみ, ADR-0046）。

用途別ロール分離（ADR-0052）:
  - migrator ロール: マイグレーション・シード（DDL/DML）を実行する。
  - app ロール: アプリケーション（web_backend / knowledge_mcp / tag_selector_mcp）が接続する。
    DML のみ、DDL 権限は持たない。
ロール作成・権限付与は常にマスター接続（DATABASE_URL / CONVERSATION_DB_URL）で行い、
マイグレーション・シードは migrator 接続で行う（10章の順序制約）。

いずれかの手順で例外が発生した場合、ログに出力の上、非0の終了コードで終了する（ADR-0018）。
全手順が成功した場合は終了コード0で終了する。テーブル単位の存在チェックによる冪等性で、
再実行しても未投入分のみが投入される。
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from urllib.parse import quote, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2 import sql
from yoyo import get_backend, read_migrations

import backfill_title_and_tags
import import_data
import seed_description_and_aliases
from db import DB
from embedding import get_embedding
from seed_helpers import (
    load_category_csv,
    load_qa_original_json,
    load_question_altered_csv,
)


DATABASE_URL = os.environ["DATABASE_URL"]
# conversation データベース（会話評価 + 検証機能, ADR-0044/0048/0051）。
# CONVERSATION_DB_NAME は存在チェック・CREATE DATABASE に使う（既定 "conversation"）。
# CONVERSATION_DB_URL は IMPL-202608261022 以降ローカル・AWS 双方で常に設定される（マスター接続）。
CONVERSATION_DB_NAME = os.environ.get("CONVERSATION_DB_NAME", "conversation")
CONVERSATION_DB_URL = os.environ.get("CONVERSATION_DB_URL", "")
# エクスポート専用読み取りロール（ADR-0046 / IMPL-202608241600 T1）。
CHATBOT_DB_NAME = os.environ.get("CHATBOT_DB_NAME", "chatbot")
EXPORT_READER_ROLE_NAME = os.environ.get("EXPORT_READER_ROLE_NAME", "chatbot_export_reader")
EXPORT_READER_PASSWORD = os.environ.get("EXPORT_READER_PASSWORD", "")

# 用途別ロール（ADR-0052 / IMPL-202608261022 T1・T5）。ローカルは docker-compose の .env、
# AWS は Terraform Secrets Manager からパスワードを注入する。パスワード未設定時はロール分離を
# 行わず、従来どおりマスター接続でマイグレーション・シードを実行する（後方互換）。
CHATBOT_MIGRATOR_ROLE_NAME = os.environ.get("CHATBOT_MIGRATOR_ROLE_NAME", "chatbot_migrator")
CHATBOT_MIGRATOR_PASSWORD = os.environ.get("CHATBOT_MIGRATOR_PASSWORD", "")
CHATBOT_APP_ROLE_NAME = os.environ.get("CHATBOT_APP_ROLE_NAME", "chatbot_app")
CHATBOT_APP_PASSWORD = os.environ.get("CHATBOT_APP_PASSWORD", "")
CONVERSATION_MIGRATOR_ROLE_NAME = os.environ.get(
    "CONVERSATION_MIGRATOR_ROLE_NAME", "conversation_migrator"
)
CONVERSATION_MIGRATOR_PASSWORD = os.environ.get("CONVERSATION_MIGRATOR_PASSWORD", "")
CONVERSATION_APP_ROLE_NAME = os.environ.get("CONVERSATION_APP_ROLE_NAME", "conversation_app")
CONVERSATION_APP_PASSWORD = os.environ.get("CONVERSATION_APP_PASSWORD", "")

# 全データインポート（全消去→上書き）バッチモード（ADR-0066）。run-task の environment
# オーバーライドで IMPORT_MODE=true と各パラメータを注入されたときのみ有効になる。通常のシード
# 起動（IMPORT_MODE 未設定）では一切実行されない＝誤って破壊的処理が走らないよう分離する。
IMPORT_MODE = os.environ.get("IMPORT_MODE", "").strip().lower() in ("1", "true", "yes")
IMPORT_TARGET = os.environ.get("IMPORT_TARGET", "both").strip()
IMPORT_BUCKET = os.environ.get("IMPORT_BUCKET", "").strip()
IMPORT_PREFIX = os.environ.get("IMPORT_PREFIX", "import").strip()
IMPORT_ROLLBACK_PREFIX = os.environ.get("IMPORT_ROLLBACK_PREFIX", "rollback").strip()
AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")

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
# ADR-0034: シード元データはイメージに /data として同梱済み。
CSV_DATA_DIR = "/" + os.environ.get("CSV_DATA_DIR", "data")
QA_ORIGINAL_FILE = os.environ["QA_ORIGINAL_FILE"]
QUESTION_ALTERED_FILE = os.environ["QUESTION_ALTERED_FILE"]
CATEGORY_FILE = os.environ["CATEGORY_FILE"]

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations"
)
# conversation データベース向け yoyo マイグレーション（ADR-0051 / IMPL-202608261022 T3・T4）。
CONVERSATION_MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations_conversation"
)


def _now():
    return datetime.now(ZoneInfo("Asia/Tokyo"))


# ---------------------------------------------------------------------------
# 接続文字列ユーティリティ（ロール差し替え・同一サーバ判定, ADR-0052）
# ---------------------------------------------------------------------------
def _swap_userinfo(url: str, user: str, password: str) -> str:
    """URL のホスト・ポート・DB名はそのままに、user/password のみ差し替えて返す。"""
    parts = urlsplit(url)
    netloc = f"{user}:{quote(password, safe='')}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _same_server(url_a: str, url_b: str) -> bool:
    """2つの接続文字列が同一の PostgreSQL サーバ（host:port）を指すか。"""
    pa, pb = urlsplit(url_a), urlsplit(url_b)
    return (pa.hostname, pa.port or 5432) == (pb.hostname, pb.port or 5432)


def migrator_database_url() -> str:
    """chatbot データベースへの migrator 接続文字列（T2）。"""
    return _swap_userinfo(DATABASE_URL, CHATBOT_MIGRATOR_ROLE_NAME, CHATBOT_MIGRATOR_PASSWORD)


def conversation_migrator_database_url() -> str:
    """conversation データベースへの migrator 接続文字列（T4）。"""
    return _swap_userinfo(
        CONVERSATION_DB_URL,
        CONVERSATION_MIGRATOR_ROLE_NAME,
        CONVERSATION_MIGRATOR_PASSWORD,
    )


# ---------------------------------------------------------------------------
# ロール分離（T1, T2, T5、ADR-0052）
# ---------------------------------------------------------------------------
def _create_or_update_login_role(cur, role_name: str, password: str) -> None:
    """LOGIN ロールを冪等に作成（既存ならパスワード更新）する（ensure_export_reader_role と同一パターン）。"""
    role = sql.Identifier(role_name)
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
    if cur.fetchone():
        cur.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD %s").format(role), (password,))
        print(f"{_now()} Role '{role_name}' already exists; password updated.")
    else:
        cur.execute(sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD %s").format(role), (password,))
        print(f"{_now()} Role '{role_name}' created.")


def _ensure_roles(
    master_url: str,
    db_name: str,
    migrator_role: str,
    migrator_password: str,
    app_role: str,
    app_password: str,
    create_vector_extension: bool = False,
) -> None:
    """migrator / app ロールを作成し、migrator に DDL 権限を付与する（マスター接続, autocommit）。

    app へのテーブル・シーケンス権限は、全テーブル作成後に _grant_app_privileges で付与する
    （GRANT ON ALL TABLES は実行時点で存在するテーブルにのみ効くため, 10章）。

    create_vector_extension=True のとき、CREATE EXTENSION vector をマスターで先に実行する。
    pgvector はトラステッド拡張ではなく非 superuser（migrator）では作成できないため、migrate() が
    migrator 接続で走る前に、マスター権限で冪等に用意しておく（migration 0001 の CREATE EXTENSION
    IF NOT EXISTS を no-op 化する）。
    """
    conn = psycopg2.connect(master_url)
    conn.autocommit = True  # 既存 ensure_export_reader_role() との一貫性（10章）
    try:
        m = sql.Identifier(migrator_role)
        a = sql.Identifier(app_role)
        dbn = sql.Identifier(db_name)
        with conn.cursor() as cur:
            if create_vector_extension:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            _create_or_update_login_role(cur, migrator_role, migrator_password)
            _create_or_update_login_role(cur, app_role, app_password)
            # マスター（接続中のロール。AWS RDS では rds_superuser で真の superuser ではない）を
            # migrator のメンバーにする。これにより、migrate が migrator 所有で作成したテーブルに対し、
            # 後段 _grant_app_privileges（マスター接続）が所有権を継承して GRANT できる（10章）。
            cur.execute("SELECT current_user")
            master_role = cur.fetchone()[0]
            cur.execute(
                sql.SQL("GRANT {} TO {}").format(m, sql.Identifier(master_role))
            )
            # migrator: マイグレーション・シードのための DDL/DML 権限。
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(dbn, m))
            cur.execute(sql.SQL("GRANT ALL ON SCHEMA public TO {}").format(m))
            cur.execute(
                sql.SQL("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {}").format(m)
            )
            cur.execute(
                sql.SQL("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {}").format(m)
            )
            # app: 接続・スキーマ利用のみ先に付与（テーブル権限は後段, 10章）。
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(dbn, a))
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(a))
    finally:
        conn.close()


def _grant_app_privileges(master_url: str, app_role: str) -> None:
    """app ロールへ全テーブル・シーケンスの DML 権限を付与する（全テーブル作成後, マスター接続）。

    DDL 権限（CREATE/ALTER/DROP TABLE）は付与しない＝app は DDL 不可（DoD 8.1, ADR-0052）。
    """
    conn = psycopg2.connect(master_url)
    conn.autocommit = True
    try:
        a = sql.Identifier(app_role)
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
                ).format(a)
            )
            # SERIAL 列（tag.id / verification_* 等）への INSERT にシーケンス権限が要る。
            cur.execute(
                sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(a)
            )
    finally:
        conn.close()


def ensure_chatbot_roles() -> None:
    """chatbot データベースに migrator / app ロールを冪等に作成する（T1, ADR-0052）。"""
    print(f"{_now()} ====== Ensuring chatbot roles (migrator / app) ...")
    _ensure_roles(
        DATABASE_URL,
        CHATBOT_DB_NAME,
        CHATBOT_MIGRATOR_ROLE_NAME,
        CHATBOT_MIGRATOR_PASSWORD,
        CHATBOT_APP_ROLE_NAME,
        CHATBOT_APP_PASSWORD,
        create_vector_extension=True,  # chatbot は question_altered.embedding で pgvector を使う
    )
    print(f"{_now()} Chatbot roles ensured.")


def grant_chatbot_app_privileges() -> None:
    print(f"{_now()} ====== Granting chatbot app privileges (DML only) ...")
    _grant_app_privileges(DATABASE_URL, CHATBOT_APP_ROLE_NAME)
    print(f"{_now()} Chatbot app privileges granted.")


def ensure_conversation_roles() -> None:
    """conversation データベースに migrator / app ロールを冪等に作成する（T5, ADR-0052）。"""
    print(f"{_now()} ====== Ensuring conversation roles (migrator / app) ...")
    _ensure_roles(
        CONVERSATION_DB_URL,
        CONVERSATION_DB_NAME,
        CONVERSATION_MIGRATOR_ROLE_NAME,
        CONVERSATION_MIGRATOR_PASSWORD,
        CONVERSATION_APP_ROLE_NAME,
        CONVERSATION_APP_PASSWORD,
    )
    print(f"{_now()} Conversation roles ensured.")


def grant_conversation_app_privileges() -> None:
    print(f"{_now()} ====== Granting conversation app privileges (DML only) ...")
    _grant_app_privileges(CONVERSATION_DB_URL, CONVERSATION_APP_ROLE_NAME)
    print(f"{_now()} Conversation app privileges granted.")


# ---------------------------------------------------------------------------
# 1. マイグレーション（chatbot / conversation）
# ---------------------------------------------------------------------------
def migrate(url: str):
    print(f"{_now()} ====== Applying migrations from {MIGRATIONS_DIR} ...")
    backend = get_backend(url)
    migrations = read_migrations(MIGRATIONS_DIR)
    with backend.lock():
        to_apply = backend.to_apply(migrations)
        backend.apply_migrations(to_apply)
    print(f"{_now()} Migrations applied ({len(to_apply)} pending step(s)).")


def migrate_conversation(url: str):
    """conversation データベースへ yoyo マイグレーションを適用する（T4, ADR-0051）。"""
    print(
        f"{_now()} ====== Applying conversation migrations from "
        f"{CONVERSATION_MIGRATIONS_DIR} ..."
    )
    backend = get_backend(url)
    migrations = read_migrations(CONVERSATION_MIGRATIONS_DIR)
    with backend.lock():
        to_apply = backend.to_apply(migrations)
        backend.apply_migrations(to_apply)
    print(f"{_now()} Conversation migrations applied ({len(to_apply)} pending step(s)).")


def ensure_conversation_database():
    """conversation データベースが無ければ作成する（AWS の同一 RDS 上のみ, ADR-0044/0051）。

    ローカル docker-compose では conversation_db が別サーバ（別コンテナ）として自身で
    データベースを保持するため、CREATE DATABASE は行わず早期リターンする（5.2節）。
    CREATE DATABASE はトランザクション不可のため autocommit=True のマスター接続で実行する。
    """
    if not _same_server(DATABASE_URL, CONVERSATION_DB_URL):
        print(
            f"{_now()} conversation database is on a separate server "
            "(local docker-compose); skipping CREATE DATABASE."
        )
        return
    print(f"{_now()} ====== Ensuring conversation database '{CONVERSATION_DB_NAME}' ...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True  # CREATE DATABASE はトランザクション不可（10章）
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (CONVERSATION_DB_NAME,)
            )
            if cur.fetchone():
                print(
                    f"{_now()} Database '{CONVERSATION_DB_NAME}' already exists. "
                    "Skipping creation."
                )
                return
            cur.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(CONVERSATION_DB_NAME))
            )
        print(f"{_now()} Database '{CONVERSATION_DB_NAME}' created.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# エクスポート専用読み取りロールの作成（ADR-0046 / IMPL-202608241600 T2）
# ---------------------------------------------------------------------------
def ensure_export_reader_role():
    """chatbot データベース向けの読み取り専用ロールを冪等に作成・権限付与する（T2, ADR-0046）。

    admin_ui のエクスポート機能が使う専用ロール。SELECT 権限のみを付与し、
    conversation データベースへの接続は禁止する（詳細は ADR-0046）。
    """
    print(f"{_now()} ====== Ensuring export reader role '{EXPORT_READER_ROLE_NAME}' ...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True  # 既存 ensure_conversation_database() との一貫性（10章）
    try:
        role = sql.Identifier(EXPORT_READER_ROLE_NAME)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (EXPORT_READER_ROLE_NAME,)
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
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {}"
                ).format(role)
            )
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
def seed_category(url: str):
    print(f"{_now()} ====== Start seeding category...")
    rows = load_category_csv(CSV_DATA_DIR, CATEGORY_FILE)
    with DB(url) as db:
        if db.exists_category():
            print(f"{_now()} category table already has data. Skipping insertion.")
            return
        if rows:
            db.insert_category(rows)
    print(f"{_now()} Inserted {len(rows)} categories.")


def seed_qa_original(url: str):
    print(f"{_now()} ====== Start seeding qa_original...")
    rows = load_qa_original_json(CSV_DATA_DIR, QA_ORIGINAL_FILE, CATEGORY_FILE)
    with DB(url) as db:
        if db.exists_qa_original():
            print(f"{_now()} qa_original table already has data. Skipping insertion.")
            return
        if rows:
            db.insert_qa_original(rows)
    print(f"{_now()} Inserted {len(rows)} qa_original rows.")


def seed_question_altered(url: str):
    print(f"{_now()} ====== Start seeding question_altered...")
    rows = load_question_altered_csv(CSV_DATA_DIR, QUESTION_ALTERED_FILE)
    with DB(url) as db:
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
def backfill_titles_and_tags(url: str):
    print(f"{_now()} ====== Start backfilling title / tags...")
    json_path = os.path.join(CSV_DATA_DIR, QA_ORIGINAL_FILE)
    items = backfill_title_and_tags.load_records(json_path)
    conn = psycopg2.connect(url)
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


def seed_tag_descriptions_and_aliases(url: str):
    print(f"{_now()} ====== Start seeding tag description / aliases (provisional)...")
    conn = psycopg2.connect(url)
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


def seed_if_empty(url: str):
    seed_category(url)
    seed_qa_original(url)
    seed_question_altered(url)
    backfill_titles_and_tags(url)
    seed_tag_descriptions_and_aliases(url)


def _resolve_import_work_urls() -> "tuple[str, str]":
    """インポート作業用の接続 URL（chatbot / conversation）を返す。

    ロール分離が有効（migrator パスワード設定済み）なら migrator 接続を、そうでなければ
    マスター接続を使う。TRUNCATE には DDL/DML 権限が要るため migrator を使う（ADR-0052/0066）。
    """
    if CHATBOT_MIGRATOR_PASSWORD:
        chatbot_url = migrator_database_url()
    else:
        chatbot_url = DATABASE_URL
    if CONVERSATION_DB_URL and CONVERSATION_MIGRATOR_PASSWORD:
        conversation_url = conversation_migrator_database_url()
    else:
        conversation_url = CONVERSATION_DB_URL
    return chatbot_url, conversation_url


def run_import_mode():
    """全データインポート（全消去→上書き）を実行して終了する（ADR-0066, IMPORT_MODE）。"""
    print(f"{_now()} ====== db_hiroba_qa_init start (IMPORT MODE, ADR-0066).")
    print(
        f"{_now()} WARNING: 破壊的モードで起動しました。対象データベースの既存データを全消去し、\n"
        f"{_now()}          S3 の投入ダンプで上書きします（事前バックアップは自動取得）。"
    )
    try:
        if not IMPORT_BUCKET:
            raise RuntimeError("IMPORT_MODE では IMPORT_BUCKET（S3 バケット名）が必須です。")
        chatbot_url, conversation_url = _resolve_import_work_urls()
        import_data.run_import(
            target=IMPORT_TARGET,
            chatbot_url=chatbot_url,
            conversation_url=conversation_url,
            bucket=IMPORT_BUCKET,
            import_prefix=IMPORT_PREFIX,
            rollback_prefix=IMPORT_ROLLBACK_PREFIX,
            region=AWS_REGION,
        )
    except Exception as exc:  # noqa: BLE001 - ワンショット処理として全例外を捕捉し非0終了する
        print(f"{_now()} ERROR: db_hiroba_qa_init import failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    print(f"{_now()} ====== db_hiroba_qa_init import completed successfully.")
    sys.exit(0)


def main():
    if IMPORT_MODE:
        run_import_mode()
        return  # run_import_mode は sys.exit する（保険で return）
    print(f"{_now()} ====== db_hiroba_qa_init start.")
    try:
        # --- chatbot: ロール分離 → migrate → seed → app 権限付与 -----------------
        chatbot_roles_enabled = bool(CHATBOT_MIGRATOR_PASSWORD and CHATBOT_APP_PASSWORD)
        if chatbot_roles_enabled:
            ensure_chatbot_roles()
            chatbot_work_url = migrator_database_url()
        else:
            print(
                f"{_now()} chatbot role passwords not set; "
                "using master connection for migrate/seed (role separation disabled)."
            )
            chatbot_work_url = DATABASE_URL

        migrate(chatbot_work_url)
        seed_if_empty(chatbot_work_url)
        if chatbot_roles_enabled:
            grant_chatbot_app_privileges()

        # --- conversation: DB作成 → ロール分離 → migrate → app 権限付与 ----------
        if CONVERSATION_DB_URL:
            ensure_conversation_database()
            conversation_roles_enabled = bool(
                CONVERSATION_MIGRATOR_PASSWORD and CONVERSATION_APP_PASSWORD
            )
            if conversation_roles_enabled:
                ensure_conversation_roles()
                conversation_work_url = conversation_migrator_database_url()
            else:
                print(
                    f"{_now()} conversation role passwords not set; "
                    "using master connection for conversation migrate."
                )
                conversation_work_url = CONVERSATION_DB_URL
            migrate_conversation(conversation_work_url)
            if conversation_roles_enabled:
                grant_conversation_app_privileges()
        else:
            print(
                f"{_now()} CONVERSATION_DB_URL is not set; skipping conversation setup."
            )

        # --- エクスポート専用読み取りロール（AWS のみ, ADR-0046） ----------------
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
