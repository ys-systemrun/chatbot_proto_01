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
        seed_if_empty()
    except Exception as exc:  # noqa: BLE001 - ワンショット処理として全例外を捕捉し非0終了する
        print(f"{_now()} ERROR: db_hiroba_qa_init failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    print(f"{_now()} ====== db_hiroba_qa_init completed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
