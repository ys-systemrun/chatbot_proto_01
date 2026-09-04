"""TagMetadataRepository（実装指示書 5.2 / T4 / ADR-0011）。

hiroba_tag ⋈ hiroba_tag_alias を全件メモリにキャッシュする（Knowledge MCP の TagRepository が
「キャッシュしない」方針なのとは対照的に、こちらは起動時ロード＋明示リロード＋定期
ポーリングでキャッシュする。ADR-0011）。

キャッシュの差し替えはアトミックに行う: 新しい辞書を構築し終えてから参照を1回の代入で
切り替える。読み取り側は最初に現在の参照をローカルへ退避してから利用するため、リロード中の
select_tags 呼び出しが「一部だけ更新された」中間状態を参照することはない。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from ...db.connection import Database
from ...models.tag import TagRecord

logger = logging.getLogger(__name__)


class TagMetadataRepository:
    def __init__(self, db_connection_factory: Database, reload_interval_sec: int):
        self._db = db_connection_factory
        self.reload_interval_sec = reload_interval_sec
        # id -> TagRecord。参照の差し替えはアトミック（GILによる単一代入）。
        self._by_id: Dict[int, TagRecord] = {}

    # ------------------------------------------------------------------ #
    # ロード / リロード
    # ------------------------------------------------------------------ #
    def load(self) -> None:
        """hiroba_tag ⋈ hiroba_tag_alias を全件読み込み、内部キャッシュを再構築する。

        新しい辞書を構築してから self._by_id を差し替える（アトミック）。
        DBアクセスに失敗した場合は、既存キャッシュを保持したままエラーをログに記録し、
        例外を呼び出し元（reload_taxonomy ハンドラ / 起動処理 / ポーリングタスク）へ伝播する。
        """
        try:
            with self._db.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        t.id,
                        t.name,
                        t.description,
                        t.parent_tag_id,
                        COALESCE(
                            array_agg(a.alias) FILTER (WHERE a.alias IS NOT NULL),
                            '{}'
                        ) AS aliases
                    FROM hiroba_tag t
                    LEFT JOIN hiroba_tag_alias a ON a.tag_id = t.id
                    GROUP BY t.id, t.name, t.description, t.parent_tag_id
                    ORDER BY t.id
                    """
                )
                rows = cur.fetchall()
        except Exception:
            logger.exception("failed to load tag taxonomy; keeping existing cache")
            raise

        new_by_id: Dict[int, TagRecord] = {}
        for tag_id, name, description, parent_tag_id, aliases in rows:
            new_by_id[tag_id] = TagRecord(
                id=tag_id,
                name=name,
                description=description,
                parent_tag_id=parent_tag_id,
                aliases=[a for a in (aliases or []) if a],
            )

        # アトミックな差し替え（この代入までは古いキャッシュが有効）
        self._by_id = new_by_id
        logger.info("tag taxonomy loaded: %d tags", len(new_by_id))

    def reload(self) -> None:
        """load() を再実行する。reload_taxonomy ツールおよび定期ポーリングタスクから呼ばれる。"""
        self.load()

    # ------------------------------------------------------------------ #
    # 参照系
    # ------------------------------------------------------------------ #
    def all_tags(self) -> List[TagRecord]:
        snapshot = self._by_id  # 参照を退避してから使う（リロードと競合させない）
        return list(snapshot.values())

    def get(self, tag_id: int) -> Optional[TagRecord]:
        return self._by_id.get(tag_id)

    def tag_count(self) -> int:
        return len(self._by_id)

    def find_tags_by_alias_match(self, query: str) -> List[TagRecord]:
        """query に含まれる文字列と aliases の一致（部分一致）を確認し、一致した TagRecord を返す。

        alias が query の部分文字列であれば一致とみなす。description/alias 未登録のタグが
        多くても例外を起こさないよう、空文字列・None は一致対象から除外する。
        """
        if not query:
            return []
        snapshot = self._by_id
        matched: List[TagRecord] = []
        for record in snapshot.values():
            for alias in record.aliases:
                if alias and alias in query:
                    matched.append(record)
                    break
        return matched
