"""シードデータ（CSV, ADR-0108）の読み込み（web_backend/src/seed_helpers.py から移管）。"""

import csv
import io
import os
from typing import List

from models import Category, QAOriginal, QuestionAltered


def resolve_csv_path(filename: str, data_dir: str) -> str:
    if not data_dir:
        raise SystemExit(
            "CSV_DATA_DIR environment variable is required and must point to a directory"
        )
    return os.path.join(data_dir, filename)


def load_category_csv(data_dir: str, category_file: str):
    category_path = resolve_csv_path(category_file, data_dir)
    rows: List[Category] = []
    with open(category_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        required = {"id", "name"}
        if not required.issubset(fieldnames):
            raise ValueError("category CSV must contain headers: id, name")
        for row in reader:
            rows.append(Category(id=int(row["id"]), name=row["name"]))
    return rows


def parse_qa_original_csv(text: str, category_ids: set) -> List[QAOriginal]:
    """QA 本体の CSV（hiroba_qa_original.csv, ADR-0108）を QAOriginal に変換する（DB 非依存の純関数）。

    必須列は uuid / question_text / answer_text。category_id は空なら None、値があれば category.csv に
    存在する ID であることを確かめる。title・category_name などほかの列はここでは読まない
    （title は backfill_title_and_tags が入れる）。
    """
    reader = csv.DictReader(io.StringIO(text))
    missing = {"uuid", "question_text", "answer_text"} - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"qa_original CSV must contain headers: {sorted(missing)}")
    rows: List[QAOriginal] = []
    for row in reader:
        rec_uuid = (row.get("uuid") or "").strip()
        if not rec_uuid:
            raise ValueError("qa_original CSV: uuid is empty")
        raw_category = (row.get("category_id") or "").strip()
        category_id = int(raw_category) if raw_category else None
        if category_id is not None and category_id not in category_ids:
            raise ValueError(
                f"Unknown category_id {category_id} in qa_original CSV ({rec_uuid}). "
                "Please add it to category.csv"
            )
        rows.append(
            QAOriginal(
                uuid=rec_uuid,
                question_text=row["question_text"],
                answer_text=row["answer_text"],
                category_id=category_id,
            )
        )
    return rows


def load_qa_original_csv(data_dir: str, qa_original_file: str, category_file: str):
    path = resolve_csv_path(qa_original_file, data_dir)
    category_ids = {c.id for c in load_category_csv(data_dir, category_file)}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return parse_qa_original_csv(f.read(), category_ids)


def load_question_altered_csv(data_dir: str, question_altered_file: str):
    question_altered_path = resolve_csv_path(question_altered_file, data_dir)
    rows: List[QuestionAltered] = []
    with open(question_altered_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        required = {"qa_id", "text"}
        if not required.issubset(fieldnames):
            raise ValueError(
                "question_altered CSV must contain headers: qa_id, text (optional id)"
            )
        has_id = "id" in fieldnames
        for row in reader:
            rows.append(
                QuestionAltered(
                    id=int(row["id"]) if has_id and row.get("id") else None,
                    qa_id=row["qa_id"],
                    text=row["text"],
                    embedding=None,
                )
            )
    return rows
