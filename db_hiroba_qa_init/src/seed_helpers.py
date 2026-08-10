"""シードデータ（CSV/JSON）の読み込み（web_backend/src/seed_helpers.py から移管）。"""

import csv
import json
import os
import uuid
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


def load_category_map(data_dir: str, category_file: str):
    categories = load_category_csv(data_dir, category_file)
    return {category.name: category.id for category in categories}


def load_qa_original_json(data_dir: str, exportjson_file: str, category_file: str):
    json_path = resolve_csv_path(exportjson_file, data_dir)
    category_map = load_category_map(data_dir, category_file)
    rows: List[QAOriginal] = []
    with open(json_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    if not isinstance(items, list):
        raise ValueError("exportjson_withguid.json must contain a top-level JSON array")

    for item in items:
        if not isinstance(item, dict):
            continue

        rec_uuid = item.get("guid") or str(uuid.uuid4())
        question_text = item.get("question") or item.get("question_text")
        answer_text = item.get("answer") or item.get("answer_text")
        if question_text is None or answer_text is None:
            raise ValueError("Each JSON record must contain 'question' and 'answer'")

        category_name = item.get("category") or item.get("category_name")
        category_id = None
        if category_name:
            category_id = category_map.get(category_name)
            if category_id is None:
                raise ValueError(
                    f"Unknown category name '{category_name}' in {exportjson_file}. "
                    f"Please add it to {category_file}"
                )

        rows.append(
            QAOriginal(
                uuid=rec_uuid,
                question_text=question_text,
                answer_text=answer_text,
                category_id=category_id,
            )
        )
    return rows


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
