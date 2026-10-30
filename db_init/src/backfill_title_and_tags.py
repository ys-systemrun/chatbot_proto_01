"""既存投入データの title / タグ補完（knowledge_mcp/migrations/backfill_title_and_tags.py から移管）。

QA_ORIGINAL_FILE（hiroba_qa_original.csv, ADR-0108）を読み込み、以下を投入する。
  1. title の補完: uuid を qa_original.uuid に突き合わせて title を UPDATE。
  2. タグの投入（2段階）:
     (a) ユニークなタグ名を tag へ INSERT ... ON CONFLICT (name) DO NOTHING（parent_tag_id は NULL）。
     (b) guid とタグ名から tag.id を引き当て、qa_tag(qa_id, tag_id) へ INSERT ... ON CONFLICT DO NOTHING。

- 冪等（何度実行しても同じ結果。ON CONFLICT DO NOTHING を活用）。存在チェックではなく
  「未設定の行のみ」を対象にするため、db_init のシードフローで毎回安全に呼べる。
- 現行の CSV にはタグの列が無いため、実運用ではタグ投入は 0 件となる（title のみ補完される）。
  将来 CSV に "tags" 列（タグ名を "|" 区切り）が付いた場合は自動的に取り込む。
- load_records は CSV の行を、backfill が扱うレコード {"guid", "title", "tags"} に読み替える
  （backfill 本体は JSON 時代と同じ）。
"""

from __future__ import annotations

import csv
from typing import List


def _normalize_tags(item: dict) -> List[str]:
    """レコードからタグ名リストを取り出す。無ければ空リスト。"""
    raw = item.get("tags", item.get("tag"))
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    tags: List[str] = []
    for t in raw:
        if t is None:
            continue
        name = str(t).strip()
        if name:
            tags.append(name)
    return tags


def load_records(csv_path: str) -> list:
    """hiroba_qa_original.csv を読み、{"guid", "title", "tags"} のレコードに読み替える。

    title が空の行は None にする（backfill は title が None の行を更新しない）。
    """
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if "uuid" not in (reader.fieldnames or []):
            raise ValueError("qa_original CSV must contain header: uuid")
        items = []
        for row in reader:
            item = {"guid": row["uuid"], "title": row.get("title") or None}
            if row.get("tags"):
                item["tags"] = row["tags"].split("|")
            items.append(item)
    return items


def backfill(conn, items: list) -> dict:
    updated_titles = 0
    tag_names: set[str] = set()

    with conn.cursor() as cur:
        # 1. title の補完
        for item in items:
            if not isinstance(item, dict):
                continue
            guid = item.get("guid")
            title = item.get("title")
            if not guid or title is None:
                continue
            cur.execute(
                "UPDATE hiroba_qa_original SET title = %s WHERE uuid = %s",
                (title, guid),
            )
            updated_titles += cur.rowcount
            tag_names.update(_normalize_tags(item))

        # 2-(a). ユニークなタグ名を投入
        for name in sorted(tag_names):
            cur.execute(
                "INSERT INTO tag (name, parent_tag_id) VALUES (%s, NULL) "
                "ON CONFLICT (name) DO NOTHING",
                (name,),
            )

        # tag.id を引き当てるためのマップ
        name_to_id: dict[str, int] = {}
        if tag_names:
            cur.execute(
                "SELECT id, name FROM tag WHERE name = ANY(%s)",
                (list(tag_names),),
            )
            for tag_id, name in cur.fetchall():
                name_to_id[name] = tag_id

        # 2-(b). QA-タグ紐付けを投入
        linked = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            guid = item.get("guid")
            if not guid:
                continue
            for name in _normalize_tags(item):
                tag_id = name_to_id.get(name)
                if tag_id is None:
                    continue
                cur.execute(
                    "INSERT INTO hiroba_qa_tag (qa_id, tag_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (guid, tag_id),
                )
                linked += cur.rowcount

    conn.commit()
    return {
        "updated_titles": updated_titles,
        "unique_tags": len(tag_names),
        "qa_tag_links": linked,
    }
