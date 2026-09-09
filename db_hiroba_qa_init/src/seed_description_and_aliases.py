"""タグ description / tag_alias の暫定シード（tag_selector_mcp/migrations/seed_description_and_aliases.py から移管）。

既存タグの一部に description と同義語（tag_alias）を DB へ直接投入する。

  1. UPDATE tag SET description = %s WHERE name = %s（対象タグに説明文を設定）
  2. INSERT INTO tag_alias (tag_id, alias) VALUES (%s, %s) ON CONFLICT (alias) DO NOTHING

- 冪等（何度実行しても同じ結果になる）。
- tag 名でタグを引き当てる（存在しないタグ名はスキップする）。

============================================================================
!!! 重要 !!!
このシードは Tag Selector MCP の MVP 動作確認用の「暫定データ」であり、
本番運用のタグ説明文・同義語の網羅的な整備ではない。本番向けの網羅的整備は、
Knowledge MCP 側のタグ管理ツール拡張が完了した後、正式な経路で登録し直す前提である。
それまでの暫定運用として DB 直接投入で対応する。
============================================================================
"""

from __future__ import annotations

from typing import Dict, List

# タグ名 -> 説明文（暫定）。要件定義書に例示されているタグを中心に最小限だけ用意する。
SEED_DESCRIPTIONS: Dict[str, str] = {
    "積算システム": "積算システムに関する情報",
    "積算システムの操作方法": "積算システムの操作手順に関する情報",
}

# タグ名 -> 同義語一覧（暫定）。質問文に含まれ得る言い換えを登録する。
SEED_ALIASES: Dict[str, List[str]] = {
    "積算システム": ["積算", "歩掛", "見積"],
    "積算システムの操作方法": ["操作方法", "使い方"],
}


def seed(conn) -> dict:
    updated_descriptions = 0
    inserted_aliases = 0
    skipped_missing_tags: List[str] = []

    with conn.cursor() as cur:
        # タグ名 -> id を引き当て
        target_names = sorted(set(SEED_DESCRIPTIONS) | set(SEED_ALIASES))
        cur.execute(
            "SELECT id, name FROM tag WHERE name = ANY(%s)",
            (target_names,),
        )
        id_by_name: Dict[str, int] = {name: tid for tid, name in cur.fetchall()}

        for name in target_names:
            if name not in id_by_name:
                skipped_missing_tags.append(name)

        # 1. description の設定（冪等: 同じ値を再設定するだけ）
        for name, description in SEED_DESCRIPTIONS.items():
            tag_id = id_by_name.get(name)
            if tag_id is None:
                continue
            cur.execute(
                "UPDATE tag SET description = %s WHERE id = %s",
                (description, tag_id),
            )
            updated_descriptions += cur.rowcount

        # 2. tag_alias の投入（冪等: ON CONFLICT (alias) DO NOTHING）
        for name, aliases in SEED_ALIASES.items():
            tag_id = id_by_name.get(name)
            if tag_id is None:
                continue
            for alias in aliases:
                cur.execute(
                    "INSERT INTO tag_alias (tag_id, alias) VALUES (%s, %s) "
                    "ON CONFLICT (alias) DO NOTHING",
                    (tag_id, alias),
                )
                inserted_aliases += cur.rowcount

    conn.commit()
    return {
        "updated_descriptions": updated_descriptions,
        "inserted_aliases": inserted_aliases,
        "skipped_missing_tags": skipped_missing_tags,
    }
