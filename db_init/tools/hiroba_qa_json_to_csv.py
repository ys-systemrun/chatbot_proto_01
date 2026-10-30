"""広場 QA 本体の JSON（exportjson_withguid.json）を、シード用 CSV（hiroba_qa_original.csv）に変換する（1回限りの加工ツール, ADR-0108）。

JSON の各レコード {guid, title, category, question, answer} を、投入先 hiroba_qa_original の列名にそろえて
uuid / title / question_text / answer_text / category_id の列に書き出す。カテゴリは名前から category.csv の ID に引き直す
（外部キーは ID で持つ）。確認用に category_name 列も書き出す（取り込みでは読み捨てる）。
レコードの並びは JSON のまま。

出力は ADR-0108 の書式（UTF-8・BOM なし・LF・全フィールドをダブルクォート）。

使い方（リポジトリルートで実行）:
    python db_init/tools/hiroba_qa_json_to_csv.py db_init/data/hiroba_qa/exportjson_withguid.json \
        db_init/data/hiroba_qa/category.csv db_init/data/hiroba_qa/hiroba_qa_original.csv
"""

from __future__ import annotations

import argparse
import csv
import json

COLUMNS = ["uuid", "title", "question_text", "answer_text", "category_id", "category_name"]


def load_category_ids(path: str) -> dict[str, str]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {row["name"]: row["id"] for row in csv.DictReader(f)}


def convert(items: list, category_ids: dict[str, str]) -> list[dict]:
    rows = []
    seen = set()
    for item in items:
        guid = item.get("guid")
        if not guid:
            raise ValueError(f"guid が無いレコードがあります: {item.get('title')!r}")
        if guid in seen:
            raise ValueError(f"guid が重複しています: {guid}")
        seen.add(guid)
        name = item.get("category") or ""
        if name and name not in category_ids:
            raise ValueError(f"category.csv に無いカテゴリです: {name!r}（{guid}）")
        rows.append({
            "uuid": guid,
            "title": item.get("title") or "",
            "question_text": item["question"],
            "answer_text": item["answer"],
            "category_id": category_ids.get(name, ""),
            "category_name": name,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("json_path", help="exportjson_withguid.json のパス")
    parser.add_argument("category_csv", help="category.csv のパス")
    parser.add_argument("out_csv", help="出力する CSV のパス")
    args = parser.parse_args()

    with open(args.json_path, encoding="utf-8") as f:
        items = json.load(f)
    rows = convert(items, load_category_ids(args.category_csv))
    with open(args.out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
