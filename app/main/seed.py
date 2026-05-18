from datetime import datetime
from zoneinfo import ZoneInfo
import os

from src.db import DB
from src.embedding import get_embedding
from src.seed_helpers import (
    load_category_csv,
    load_question_altered_csv,
    load_qa_original_json,
)


EXPORTJSON_FILE = os.environ.get("EXPORTJSON_FILE", "exportjson_withguid.json")
QUESTION_ALTERED_FILE = os.environ.get("QUESTION_ALTERED_FILE", "question_altered.csv")
CATEGORY_FILE = os.environ.get("CATEGORY_FILE", "category.csv")

DATABASE_URL = os.environ["DATABASE_URL"]
EMBEDDING_URL = os.environ["LMSTUDIO_EMBEDDING_URL"]
EMBEDDING_MODEL = os.environ["MODEL_EMBEDDING"]
CSV_DATA_DIR = "/" + os.environ["CSV_DATA_DIR"]


def main_seed_question_altered():
    print(datetime.now(ZoneInfo("Asia/Tokyo")))
    print("\n====== Start seeding question_altered...\n\n")
    question_altered_rows = load_question_altered_csv(
        CSV_DATA_DIR, QUESTION_ALTERED_FILE
    )
    for row in question_altered_rows:
        if row.embedding is None:
            row.embedding = get_embedding(EMBEDDING_URL, EMBEDDING_MODEL, row.text)

    with DB(DATABASE_URL) as db:
        if db.exists_question_altered():
            print(datetime.now(ZoneInfo("Asia/Tokyo")))
            print("question_altered table already has data. Skipping insertion.")
            return
        if question_altered_rows:
            db.insert_question_altered(question_altered_rows)
    print(datetime.now(ZoneInfo("Asia/Tokyo")))
    print(f"Inserted {len(question_altered_rows)} question_altered rows.")


def main_seed_qa_original():
    print(datetime.now(ZoneInfo("Asia/Tokyo")))
    print("\n====== Start seeding qa_original...\n\n")
    qa_original_rows = load_qa_original_json(
        CSV_DATA_DIR, EXPORTJSON_FILE, CATEGORY_FILE
    )
    with DB(DATABASE_URL) as db:
        if db.exists_qa_original():
            print(datetime.now(ZoneInfo("Asia/Tokyo")))
            print("qa_original table already has data. Skipping insertion.")
            return
        if qa_original_rows:
            db.insert_qa_original(qa_original_rows)
    print(datetime.now(ZoneInfo("Asia/Tokyo")))
    print(f"Inserted {len(qa_original_rows)} qa_original rows.")


def main_seed_category():
    print(datetime.now(ZoneInfo("Asia/Tokyo")))
    print("\n====== Start seeding category...\n\n")
    category_rows = load_category_csv(
        CSV_DATA_DIR, CATEGORY_FILE
    )
    with DB(DATABASE_URL) as db:
        if db.exists_category():
            print(datetime.now(ZoneInfo("Asia/Tokyo")))
            print("category table already has data. Skipping insertion.")
            return
        if category_rows:
            db.insert_category(category_rows)
    print(datetime.now(ZoneInfo("Asia/Tokyo")))
    print(f"Inserted {len(category_rows)} categories.")

def main_seed_all():
    main_seed_category()
    main_seed_qa_original()
    main_seed_question_altered()

