"""既存投入データの title / タグ補完（knowledge_mcp/migrations/backfill_title_and_tags.py から移管）。

QA_ORIGINAL_FILE（exportjson_withguid.json 等）を読み込み、以下を投入する。
  1. title の補完: guid を qa_original.uuid に突き合わせて title を UPDATE。
  2. タグの投入（2段階）:
     (a) ユニークなタグ名を tag へ INSERT ... ON CONFLICT (name) DO NOTHING（parent_tag_id は NULL）。
     (b) guid とタグ名から tag.id を引き当て、qa_tag(qa_id, tag_id) へ INSERT ... ON CONFLICT DO NOTHING。

- 冪等（何度実行しても同じ結果。ON CONFLICT DO NOTHING を活用）。存在チェックではなく
  「未設定の行のみ」を対象にするため、db_hiroba_qa_init のシードフローで毎回安全に呼べる。
- 現行の exportjson_withguid.json にはレコード単位の "tags" フィールドが無いため、
  実運用ではタグ投入は 0 件となる（title のみ補完される）。将来 JSON にタグが付与された場合、
  レコードの "tags"（配列）または "tag" を自動的に取り込む。
"""

from __future__ import annotations

import json
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


def load_records(json_path: str) -> list:
    with open(json_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    if not isinstance(items, list):
        raise ValueError("exportjson must contain a top-level JSON array")
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
                "UPDATE qa_original SET title = %s WHERE uuid = %s",
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
                    "INSERT INTO qa_tag (qa_id, tag_id) VALUES (%s, %s) "
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
