"""広場 QA 本体の CSV（hiroba_qa_original.csv, ADR-0108）の読み込みの単体テスト。

DB には触れず、CSV → QAOriginal の変換（必須列・カテゴリ ID の検証・BOM 付きの読み込み）と、
title 補完用のレコードへの読み替え（backfill_title_and_tags.load_records）を検証する。
"""

import csv
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import backfill_title_and_tags
import seed_helpers

HEADER = '"uuid","title","question_text","answer_text","category_id","category_name"'


def test_parse_qa_original_csv_maps_columns_and_category_id():
    text = (
        HEADER + "\n"
        '"u-1","見積書の複製","複製したい","［複写］ボタンで複製します。\n2行目","3","名前は読み捨て"\n'
        '"u-2","カテゴリなし","q","a","",""\n'
    )
    rows = seed_helpers.parse_qa_original_csv(text, {3})
    assert [r.uuid for r in rows] == ["u-1", "u-2"]
    assert rows[0].question_text == "複製したい"
    assert rows[0].answer_text == "［複写］ボタンで複製します。\n2行目"
    assert rows[0].category_id == 3
    assert rows[1].category_id is None


def test_parse_qa_original_csv_rejects_unknown_category_and_missing_columns():
    with pytest.raises(ValueError):
        seed_helpers.parse_qa_original_csv(HEADER + '\n"u-1","t","q","a","99",""\n', {1})
    with pytest.raises(ValueError):
        seed_helpers.parse_qa_original_csv('"uuid","title"\n"u-1","t"\n', {1})
    with pytest.raises(ValueError):
        seed_helpers.parse_qa_original_csv(HEADER + '\n"","t","q","a","",""\n', {1})


def test_load_qa_original_csv_reads_bom_file(tmp_path):
    (tmp_path / "category.csv").write_text("id,name\n1,カテゴリ\n", encoding="utf-8")
    (tmp_path / "qa.csv").write_text(HEADER + '\n"u-1","t","q","a","1","カテゴリ"\n', encoding="utf-8-sig")
    rows = seed_helpers.load_qa_original_csv(str(tmp_path), "qa.csv", "category.csv")
    assert rows[0].uuid == "u-1" and rows[0].category_id == 1


def test_backfill_load_records_reads_uuid_title_and_tags(tmp_path):
    path = tmp_path / "qa.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")
        w.writerow(["uuid", "title", "question_text", "answer_text", "category_id", "tags"])
        w.writerow(["u-1", "タイトル", "q", "a", "", "タグA|タグB"])
        w.writerow(["u-2", "", "q", "a", "", ""])
    items = backfill_title_and_tags.load_records(str(path))
    assert items == [
        {"guid": "u-1", "title": "タイトル", "tags": ["タグA", "タグB"]},
        {"guid": "u-2", "title": None},
    ]


def test_real_seed_csv_if_present():
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    if not os.path.exists(os.path.join(data_dir, "hiroba_qa", "hiroba_qa_original.csv")):
        pytest.skip("hiroba_qa_original.csv is not pulled (dvc pull)")
    rows = seed_helpers.load_qa_original_csv(data_dir, "hiroba_qa/hiroba_qa_original.csv", "hiroba_qa/category.csv")
    assert len(rows) == 825
    assert len({r.uuid for r in rows}) == len(rows)
    assert all(r.category_id is not None for r in rows)
