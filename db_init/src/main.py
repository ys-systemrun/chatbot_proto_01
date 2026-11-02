"""db_init エントリポイント（IMPL-202608061016、IMPL-202608261022 で拡張）。

処理順序:
  1. knowledge ロール分離: migrator / app ロールを作成（マスター接続, ADR-0052）。
  2. knowledge マイグレーション適用（yoyo, migrator 接続, ADR-0017）。
  3. knowledge シード（hiroba_category / hiroba_qa_original / hiroba_question_altered / backfill / tag 説明 /
     トラブルシューティング記事 HTML インポート, migrator 接続）。
  4. knowledge app ロールへ DML 権限を付与（全テーブル作成後, マスター接続）。
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

実行モード（environment オーバーライドで切替, ADR-0066/0075）:
  - 通常起動（未設定）: 上記6ステップを全て実行する。
  - MIGRATE_ONLY=true（ADR-0075）: 手順3（knowledge シード投入）のみをスキップし、それ以外の
    手順1・2・4・5・6は通常どおり実行する。スキーマ変更のみを反映したいとき（データ投入は後日
    import-data で行う）に使う。非破壊的。
  - IMPORT_MODE=true（ADR-0066）: 通常フローを実行せず、全消去→上書き投入バッチのみを実行する。
    IMPORT_FORMAT=csv（ADR-0109）なら SQL ダンプではなく CSV スナップショットを、IMPORT_BUCKET の
    <IMPORT_PREFIX>/<db>/ か IMPORT_DIR（ローカル）から取り込む。スキーマ版・投入先の版の照合に
    合わなければ中止する（IMPORT_FORCE=true で続行）。埋め込みはキャッシュ（/data/embedding_cache）から補う。
  - QUERY_MODE=true（ADR-0083）: 通常フローを実行せず、QUERY_SQL に渡されたアドホック SQL を
    QUERY_TARGET_DB（knowledge / conversation / both）へマスター接続で1トランザクション実行する。
    SELECT 結果（最終文のみ）または影響行数を標準出力へ出力する。
  - EXPORT_MODE=true（ADR-0103）: 通常フローを実行せず、両データベースの対象テーブルを読み取り専用で
    退避 SQL（TRUNCATE + INSERT）にし、マニフェストとともに IMPORT_BUCKET の export/<EXPORT_TIMESTAMP>/ へ
    置く。EXPORT_MANIFEST_ONLY=true なら SQL を作らずマニフェスト（行数・スキーマ版）だけを置く。
    EXPORT_FORMAT=csv（ADR-0109）なら SQL ではなくテーブルごとの CSV スナップショット（COPY 形式）と
    マニフェストを、IMPORT_BUCKET の snapshot/<EXPORT_TIMESTAMP>/ か、EXPORT_DIR（ローカル）へ置く。
  IMPORT_MODE / QUERY_MODE / EXPORT_MODE / MIGRATE_ONLY は排他。2 つ以上を指定すると起動時にエラー終了する。
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

import export_data
import import_data
import snapshot_export
import snapshot_import
import troubleshooting_import
from embedding import get_embedding


DATABASE_URL = os.environ["DATABASE_URL"]
# conversation データベース（会話評価 + 検証機能, ADR-0044/0048/0051）。
# CONVERSATION_DB_NAME は存在チェック・CREATE DATABASE に使う（既定 "conversation"）。
# CONVERSATION_DB_URL は IMPL-202608261022 以降ローカル・AWS 双方で常に設定される（マスター接続）。
CONVERSATION_DB_NAME = os.environ.get("CONVERSATION_DB_NAME", "conversation")
CONVERSATION_DB_URL = os.environ.get("CONVERSATION_DB_URL", "")
# エクスポート専用読み取りロール（ADR-0046 / IMPL-202608241600 T1）。
KNOWLEDGE_DB_NAME = os.environ.get("KNOWLEDGE_DB_NAME", "db_chatbot_knowledge_base")
EXPORT_READER_ROLE_NAME = os.environ.get("EXPORT_READER_ROLE_NAME", "knowledge_export_reader")
EXPORT_READER_PASSWORD = os.environ.get("EXPORT_READER_PASSWORD", "")

# 用途別ロール（ADR-0052 / IMPL-202608261022 T1・T5）。ローカルは docker-compose の .env、
# AWS は Terraform Secrets Manager からパスワードを注入する。パスワード未設定時はロール分離を
# 行わず、従来どおりマスター接続でマイグレーション・シードを実行する（後方互換）。
KNOWLEDGE_MIGRATOR_ROLE_NAME = os.environ.get("KNOWLEDGE_MIGRATOR_ROLE_NAME", "knowledge_migrator")
KNOWLEDGE_MIGRATOR_PASSWORD = os.environ.get("KNOWLEDGE_MIGRATOR_PASSWORD", "")
KNOWLEDGE_APP_ROLE_NAME = os.environ.get("KNOWLEDGE_APP_ROLE_NAME", "knowledge_app")
KNOWLEDGE_APP_PASSWORD = os.environ.get("KNOWLEDGE_APP_PASSWORD", "")
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
# マイグレーション専用モード（ADR-0075）。run-task の environment オーバーライドで
# MIGRATE_ONLY=true を注入されたときのみ有効になる。通常のシード起動（未設定）では既存動作を
# 完全に維持する（後方互換）。真の場合、main() の6ステップのうち knowledge シード投入（手順3）
# のみをスキップし、ロール作成・マイグレーション適用・権限付与・エクスポート専用ロール作成は
# 通常どおり実行する。IMPORT_MODE と同じ真偽値判定方式を踏襲する。
MIGRATE_ONLY = os.environ.get("MIGRATE_ONLY", "").strip().lower() in ("1", "true", "yes")
# アドホック SQL 実行モード（ADR-0083）。run-task の environment オーバーライドで QUERY_MODE=true と
# QUERY_TARGET_DB / QUERY_SQL を注入されたときのみ有効になる。通常起動（未設定）では一切実行されない。
# IMPORT_MODE / MIGRATE_ONLY と同じ真偽値判定方式を踏襲する。
QUERY_MODE = os.environ.get("QUERY_MODE", "").strip().lower() in ("1", "true", "yes")
# 実行対象データベース（knowledge | conversation | both）。既定は knowledge（QA・タグ等の参照・保守が主用途）。
QUERY_TARGET_DB = os.environ.get("QUERY_TARGET_DB", "knowledge").strip()
# 実行する SQL 本文（全文）。セミコロン区切りで複数文を含みうる。
QUERY_SQL = os.environ.get("QUERY_SQL", "")
# 退避エクスポートモード（ADR-0103）。run-task の environment オーバーライドで EXPORT_MODE=true と
# EXPORT_TIMESTAMP を注入されたときのみ有効になる。読み取り専用（データは変更しない）。
EXPORT_MODE = os.environ.get("EXPORT_MODE", "").strip().lower() in ("1", "true", "yes")
EXPORT_MANIFEST_ONLY = os.environ.get("EXPORT_MANIFEST_ONLY", "").strip().lower() in ("1", "true", "yes")
EXPORT_TIMESTAMP = os.environ.get("EXPORT_TIMESTAMP", "").strip()
EXPORT_PREFIX = os.environ.get("EXPORT_PREFIX", "").strip()
# 書き出しの形式（ADR-0109）。sql（既定, ADR-0103 の退避 SQL）/ csv（テーブルごとの CSV スナップショット）。
EXPORT_FORMAT = os.environ.get("EXPORT_FORMAT", "sql").strip().lower()
# csv のときの書き出し先（ローカル実行用）。指定があれば S3 ではなくこのディレクトリへ書く。
EXPORT_DIR = os.environ.get("EXPORT_DIR", "").strip()
IMPORT_TARGET = os.environ.get("IMPORT_TARGET", "both").strip()
IMPORT_BUCKET = os.environ.get("IMPORT_BUCKET", "").strip()
IMPORT_PREFIX = os.environ.get("IMPORT_PREFIX", "import").strip()
IMPORT_ROLLBACK_PREFIX = os.environ.get("IMPORT_ROLLBACK_PREFIX", "rollback").strip()
# 取り込みの形式（ADR-0109）。sql（既定, ADR-0066 の SQL ダンプ）/ csv（CSV スナップショット）。
IMPORT_FORMAT = os.environ.get("IMPORT_FORMAT", "sql").strip().lower()
# csv のときの取り込み元（ローカル実行用）。<IMPORT_DIR>/<db>/manifest.json と CSV を読む。
IMPORT_DIR = os.environ.get("IMPORT_DIR", "").strip()
# 照合（スキーマ版・投入先が記録した版のままか）に合わなくても続行する（ADR-0109 §6）。
IMPORT_FORCE = os.environ.get("IMPORT_FORCE", "").strip().lower() in ("1", "true", "yes")
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
# ADR-0109: knowledge DB のスナップショットは /data/knowledge/、埋め込みキャッシュは /data/embedding_cache/。
CSV_DATA_DIR = "/" + os.environ.get("CSV_DATA_DIR", "data")
# イメージに同梱したシード元データの版（ADR-0097）。ローカル実行では未設定。
KB_DATA_VERSION = os.environ.get("KB_DATA_VERSION", "")

# 追加用のトラブルシューティング記事（ADR-0105 / ADR-0109 §9）。スナップショットに含まれていない
# 新しい情報源だけを置き、(source_key, title) で未投入の記事だけを入れる。取り込まれた後は
# スナップショット（次の kb-export）が正本になる。(CSV_DATA_DIR からの相対パス, source_key)。
TROUBLESHOOTING_SOURCES = [
    ("redmine_error_taiou/redmine_error_taiou.csv", "redmine_error_taiou"),
]

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
    """ナレッジ データベースへの migrator 接続文字列（T2）。"""
    return _swap_userinfo(DATABASE_URL, KNOWLEDGE_MIGRATOR_ROLE_NAME, KNOWLEDGE_MIGRATOR_PASSWORD)


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


def ensure_knowledge_roles() -> None:
    """ナレッジ データベースに migrator / app ロールを冪等に作成する（T1, ADR-0052）。"""
    print(f"{_now()} ====== Ensuring knowledge roles (migrator / app) ...")
    _ensure_roles(
        DATABASE_URL,
        KNOWLEDGE_DB_NAME,
        KNOWLEDGE_MIGRATOR_ROLE_NAME,
        KNOWLEDGE_MIGRATOR_PASSWORD,
        KNOWLEDGE_APP_ROLE_NAME,
        KNOWLEDGE_APP_PASSWORD,
        create_vector_extension=True,  # knowledge は question_altered.embedding で pgvector を使う
    )
    print(f"{_now()} Chatbot roles ensured.")


def grant_knowledge_app_privileges() -> None:
    print(f"{_now()} ====== Granting knowledge app privileges (DML only) ...")
    _grant_app_privileges(DATABASE_URL, KNOWLEDGE_APP_ROLE_NAME)
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
# 1. マイグレーション（knowledge / conversation）
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
    """ナレッジ データベース向けの読み取り専用ロールを冪等に作成・権限付与する（T2, ADR-0046）。

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
                    sql.Identifier(KNOWLEDGE_DB_NAME), role
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
# シード（ADR-0109 段階 4: 空の knowledge DB へのスナップショットの取り込み + 追加分）
# ---------------------------------------------------------------------------
def seed_knowledge_snapshot(url: str):
    """knowledge DB が空なら、イメージ同梱のスナップショット（/data/knowledge）を取り込む。

    データがあれば何もしない（取り込み直しは kb-import で明示的に行う）。スキーマ版が合わなければ
    失敗する（マイグレーションを追加したら、スナップショットを書き出し直す, ADR-0109）。
    埋め込みはキャッシュ（/data/embedding_cache）から補う。
    """
    print(f"{_now()} ====== Start seeding knowledge snapshot...")
    if not os.path.exists(os.path.join(CSV_DATA_DIR, "knowledge", export_data.MANIFEST_FILE)):
        print(f"{_now()} knowledge snapshot not found in {CSV_DATA_DIR}/knowledge; skipping.")
        return
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            has_data = snapshot_import._has_data(cur, import_data.tables_for("knowledge"))
        conn.rollback()
    finally:
        conn.close()
    if has_data:
        print(f"{_now()} knowledge tables already have data. Skipping snapshot import.")
        return
    snapshot_import.run_snapshot_import(
        target="knowledge",
        knowledge_url=url,
        conversation_url="",
        timestamp=_now().strftime("%Y%m%d%H%M%S"),
        directory=CSV_DATA_DIR,
        cache_root=os.path.join(CSV_DATA_DIR, "embedding_cache"),
        model_id=EMBEDDING_MODEL,
    )


def _embed_fn():
    """埋め込みの計算関数（記事・言い換え質問文で共通の設定。EMBEDDING_PROVIDER に従う）。"""

    def embed(text: str) -> list[float]:
        return get_embedding(
            EMBEDDING_PROVIDER,
            EMBEDDING_URL,
            EMBEDDING_MODEL,
            text,
            BEDROCK_REGION,
        )

    return embed


def seed_troubleshooting_articles(url: str):
    """トラブルシューティング記事 CSV を冪等投入する（ADR-0076 / ADR-0078 / ADR-0105 / ADR-0108 / 10章）。

    (source_key, title) の存在チェックで既存レコードは上書きしない。未投入の記事だけに
    embedding を計算して INSERT する。ソースファイルが無い環境（開発用最小構成等）はスキップする。
    """
    print(f"{_now()} ====== Start seeding troubleshooting articles...")
    articles = []
    for filename, source_key in TROUBLESHOOTING_SOURCES:
        path = os.path.join(CSV_DATA_DIR, filename)
        if not os.path.exists(path):
            print(
                f"{_now()} troubleshooting source not found, skipping: {path}"
            )
            continue
        # セル内改行を保つため newline="" で読む（csv モジュールの作法）。BOM 付きでも読めるようにする。
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            parsed = troubleshooting_import.parse_csv_articles(f.read(), source_key)
        print(f"{_now()} parsed {len(parsed)} article(s) from {filename}.")
        articles.extend(parsed)

    if not articles:
        print(f"{_now()} no troubleshooting articles to seed. Skipping.")
        return

    conn = psycopg2.connect(url)
    try:
        stats = troubleshooting_import.import_articles(
            conn, articles, _embed_fn()
        )
    finally:
        conn.close()
    for warning in stats["warnings"]:
        print(f"{_now()} WARNING: {warning}")
    print(
        f"{_now()} troubleshooting seed done: "
        f"inserted={stats['inserted']}, "
        f"backfilled_embeddings={stats['backfilled_embeddings']}, "
        f"backfilled_uuids={stats['backfilled_uuids']}, "
        f"skipped_existing={stats['skipped_existing']}."
    )


def seed_if_empty(url: str):
    seed_knowledge_snapshot(url)
    seed_troubleshooting_articles(url)
    # キャッシュに無かった埋め込み（別モデルのローカル環境・本番で欠けていた記事など）を計算して埋める。
    print(f"{_now()} ====== Start backfilling missing embeddings...")
    snapshot_import.backfill_missing_embeddings(url, _embed_fn())


def _resolve_import_work_urls() -> "tuple[str, str]":
    """インポート作業用の接続 URL（knowledge / conversation）を返す。

    ロール分離が有効（migrator パスワード設定済み）なら migrator 接続を、そうでなければ
    マスター接続を使う。TRUNCATE には DDL/DML 権限が要るため migrator を使う（ADR-0052/0066）。
    """
    if KNOWLEDGE_MIGRATOR_PASSWORD:
        knowledge_url = migrator_database_url()
    else:
        knowledge_url = DATABASE_URL
    if CONVERSATION_DB_URL and CONVERSATION_MIGRATOR_PASSWORD:
        conversation_url = conversation_migrator_database_url()
    else:
        conversation_url = CONVERSATION_DB_URL
    return knowledge_url, conversation_url


def run_import_mode():
    """全データインポート（全消去→上書き）を実行して終了する（ADR-0066, IMPORT_MODE）。"""
    print(f"{_now()} ====== db_init start (IMPORT MODE, ADR-0066).")
    print(
        f"{_now()} WARNING: 破壊的モードで起動しました。対象データベースの既存データを全消去し、\n"
        f"{_now()}          S3 の投入ダンプで上書きします（事前バックアップは自動取得）。"
    )
    try:
        if IMPORT_FORMAT not in ("sql", "csv"):
            raise RuntimeError(f"IMPORT_FORMAT は sql / csv のいずれかです: {IMPORT_FORMAT!r}")
        if not IMPORT_BUCKET and not (IMPORT_FORMAT == "csv" and IMPORT_DIR):
            raise RuntimeError("IMPORT_MODE では IMPORT_BUCKET（S3 バケット名）が必須です（csv は IMPORT_DIR でも可）。")
        knowledge_url, conversation_url = _resolve_import_work_urls()
        if IMPORT_FORMAT == "csv":
            snapshot_import.run_snapshot_import(
                target=IMPORT_TARGET,
                knowledge_url=knowledge_url,
                conversation_url=conversation_url,
                timestamp=_now().strftime("%Y%m%d%H%M%S"),
                directory=IMPORT_DIR or None,
                bucket=IMPORT_BUCKET or None,
                prefix=IMPORT_PREFIX,
                rollback_prefix=IMPORT_ROLLBACK_PREFIX,
                region=AWS_REGION,
                force=IMPORT_FORCE,
                cache_root=os.path.join(CSV_DATA_DIR, "embedding_cache"),
                model_id=EMBEDDING_MODEL,
            )
            if "knowledge" in import_data.parse_targets(IMPORT_TARGET):
                snapshot_import.backfill_missing_embeddings(knowledge_url, _embed_fn())
        else:
            import_data.run_import(
                target=IMPORT_TARGET,
                knowledge_url=knowledge_url,
                conversation_url=conversation_url,
                bucket=IMPORT_BUCKET,
                import_prefix=IMPORT_PREFIX,
                rollback_prefix=IMPORT_ROLLBACK_PREFIX,
                region=AWS_REGION,
            )
    except Exception as exc:  # noqa: BLE001 - ワンショット処理として全例外を捕捉し非0終了する
        print(f"{_now()} ERROR: db_init import failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    print(f"{_now()} ====== db_init import completed successfully.")
    sys.exit(0)


def run_export_mode():
    """退避エクスポートを実行して終了する（ADR-0103, EXPORT_MODE）。読み取り専用。"""
    print(f"{_now()} ====== db_init start (EXPORT MODE, ADR-0103).")
    try:
        if EXPORT_FORMAT not in ("sql", "csv"):
            raise RuntimeError(f"EXPORT_FORMAT は sql / csv のいずれかです: {EXPORT_FORMAT!r}")
        if not IMPORT_BUCKET and not (EXPORT_FORMAT == "csv" and EXPORT_DIR):
            raise RuntimeError("EXPORT_MODE では IMPORT_BUCKET（S3 バケット名）が必須です（csv は EXPORT_DIR でも可）。")
        if not EXPORT_TIMESTAMP:
            raise RuntimeError("EXPORT_MODE では EXPORT_TIMESTAMP（退避の識別子）が必須です。")
        knowledge_url, conversation_url = _resolve_import_work_urls()
        if EXPORT_FORMAT == "csv":
            snapshot_export.run_snapshot_export(
                knowledge_url=knowledge_url,
                conversation_url=conversation_url,
                timestamp=EXPORT_TIMESTAMP,
                bucket=IMPORT_BUCKET or None,
                prefix=EXPORT_PREFIX or "snapshot",
                directory=EXPORT_DIR or None,
                region=AWS_REGION,
            )
        else:
            export_data.run_export(
                knowledge_url=knowledge_url,
                conversation_url=conversation_url,
                bucket=IMPORT_BUCKET,
                timestamp=EXPORT_TIMESTAMP,
                prefix=EXPORT_PREFIX or "export",
                manifest_only=EXPORT_MANIFEST_ONLY,
                region=AWS_REGION,
            )
    except Exception as exc:  # noqa: BLE001 - ワンショット処理として全例外を捕捉し非0終了する
        print(f"{_now()} ERROR: db_init export failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    print(f"{_now()} ====== db_init export completed successfully.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# アドホック SQL 実行モード（ADR-0083, QUERY_MODE）
# ---------------------------------------------------------------------------
def _query_targets() -> "list[tuple[str, str]]":
    """QUERY_TARGET_DB に対応する (ラベル, マスター接続 URL) の実行順リストを返す。

    both 指定時は knowledge -> conversation の順で返す（同一 SQL を逐次実行する, ADR-0083）。
    """
    if QUERY_TARGET_DB == "knowledge":
        return [("knowledge", DATABASE_URL)]
    if QUERY_TARGET_DB == "conversation":
        if not CONVERSATION_DB_URL:
            raise RuntimeError(
                "QUERY_TARGET_DB=conversation ですが CONVERSATION_DB_URL が未設定です。"
            )
        return [("conversation", CONVERSATION_DB_URL)]
    if QUERY_TARGET_DB == "both":
        if not CONVERSATION_DB_URL:
            raise RuntimeError(
                "QUERY_TARGET_DB=both ですが CONVERSATION_DB_URL が未設定です。"
            )
        return [("knowledge", DATABASE_URL), ("conversation", CONVERSATION_DB_URL)]
    raise RuntimeError(
        f"QUERY_TARGET_DB は knowledge / conversation / both のいずれか（指定: {QUERY_TARGET_DB!r}）。"
    )


def _run_query_on(label: str, url: str) -> None:
    """1つのデータベースへ QUERY_SQL を1トランザクションで実行し、結果を標準出力へ整形出力する。

    psycopg2 はパラメータなしの execute() では単純クエリプロトコルを使うため複数文を実行できるが、
    cursor.description（結果セットの有無・列情報）は最後の文のもののみが残る。よって画面に表示する
    結果セットは最終文が返した行のみとする（ADR-0083）。正常終了時に commit、例外時は rollback する。
    """
    print(f"{_now()} ====== [{label}] QUERY 実行開始")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(QUERY_SQL)
            if cur.description is not None:
                # 最終文が結果セットを持つ（SELECT 等）。ヘッダ行＋各行をタブ区切りで出力する。
                columns = [d[0] for d in cur.description]
                rows = cur.fetchall()
                print("\t".join(columns))
                for row in rows:
                    print("\t".join("" if v is None else str(v) for v in row))
                print(f"{_now()} [{label}] {len(rows)} row(s) returned.")
            else:
                # 結果セットを持たない（UPDATE/DELETE/DDL 等）。影響行数（最終文）のみ出力する。
                print(f"{_now()} [{label}] no result set (rowcount={cur.rowcount}).")
        conn.commit()
        print(f"{_now()} [{label}] committed.")
    except Exception:
        conn.rollback()
        print(f"{_now()} [{label}] rolled back due to error.", file=sys.stderr)
        raise
    finally:
        conn.close()


def run_query_mode():
    """アドホック SQL を実行して終了する（ADR-0083, QUERY_MODE）。

    QUERY_TARGET_DB で指定されたデータベースへ、対応するマスター接続で QUERY_SQL を実行する。
    both 指定時は knowledge -> conversation の順に同一 SQL を逐次実行し、対象ごとに区切って結果を出力する。
    いずれかの対象で例外が発生した場合、rollback の上、ログ出力して非0終了する。
    """
    print(
        f"{_now()} ====== db_init start (QUERY MODE, ADR-0083). "
        f"target={QUERY_TARGET_DB}"
    )
    try:
        if not QUERY_SQL.strip():
            raise RuntimeError("QUERY_MODE では QUERY_SQL（実行する SQL 本文）が必須です。")
        for label, url in _query_targets():
            _run_query_on(label, url)
    except Exception as exc:  # noqa: BLE001 - ワンショット処理として全例外を捕捉し非0終了する
        print(f"{_now()} ERROR: db_init query failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    print(f"{_now()} ====== db_init query completed successfully.")
    sys.exit(0)


def _check_exclusive_modes() -> None:
    """起動モードの同時指定を拒否する（ADR-0103: 読み取り専用の EXPORT_MODE と破壊的モードを混ぜない）。"""
    enabled = [
        name
        for name, on in (
            ("IMPORT_MODE", IMPORT_MODE),
            ("QUERY_MODE", QUERY_MODE),
            ("EXPORT_MODE", EXPORT_MODE),
            ("MIGRATE_ONLY", MIGRATE_ONLY),
        )
        if on
    ]
    if len(enabled) > 1:
        print(
            f"{_now()} ERROR: 起動モードは 1 つだけ指定してください（指定: {', '.join(enabled)}）。",
            file=sys.stderr,
        )
        sys.exit(1)


def main():
    _check_exclusive_modes()
    if EXPORT_MODE:
        run_export_mode()
        return  # run_export_mode は sys.exit する（保険で return）
    if QUERY_MODE:
        run_query_mode()
        return  # run_query_mode は sys.exit する（保険で return）
    if IMPORT_MODE:
        run_import_mode()
        return  # run_import_mode は sys.exit する（保険で return）
    print(f"{_now()} ====== db_init start.")
    print(f"{_now()} seed data version (KB_DATA_VERSION): {KB_DATA_VERSION or '(not set)'}")
    try:
        # --- knowledge: ロール分離 → migrate → seed → app 権限付与 -----------------
        knowledge_roles_enabled = bool(KNOWLEDGE_MIGRATOR_PASSWORD and KNOWLEDGE_APP_PASSWORD)
        if knowledge_roles_enabled:
            ensure_knowledge_roles()
            knowledge_work_url = migrator_database_url()
        else:
            print(
                f"{_now()} knowledge role passwords not set; "
                "using master connection for migrate/seed (role separation disabled)."
            )
            knowledge_work_url = DATABASE_URL

        migrate(knowledge_work_url)
        if MIGRATE_ONLY:
            print(
                f"{_now()} MIGRATE_ONLY is set; skipping knowledge seed insertion "
                "(ADR-0075). Roles / migrations / grants are still applied."
            )
        else:
            seed_if_empty(knowledge_work_url)
        if knowledge_roles_enabled:
            grant_knowledge_app_privileges()

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
        print(f"{_now()} ERROR: db_init failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    print(f"{_now()} ====== db_init completed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
