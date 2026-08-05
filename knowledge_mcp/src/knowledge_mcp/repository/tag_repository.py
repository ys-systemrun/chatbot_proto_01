"""TagRepository（実装指示書 5.6 / ADR-0006）。

tag / qa_tag テーブルへの CRUD を提供する。
**内部状態としてタグ情報をキャッシュしてはならない**（呼び出しの都度SQLでDBを参照する）。
外部から tag テーブルが直接変更された場合でも、再起動なしに最新内容を返すため。
"""

from __future__ import annotations

from typing import List, Optional

from ..db.connection import Database
from ..models.tag import TagNode


class TagError(Exception):
    """タグ操作の業務エラー（循環参照・参照制約違反・重複等）。"""


class TagRepository:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------ #
    # 参照系
    # ------------------------------------------------------------------ #
    def list_tags(self, parent_tag_id: Optional[int] = None) -> List[TagNode]:
        """タグを木構造で返す。

        parent_tag_id が None のときはルート（parent_tag_id IS NULL）を起点、
        指定時はそのタグの直下の子を起点として、各ノードに子孫をネストして返す。
        毎回テーブル全体を1クエリで読み直す（キャッシュしない）。
        """
        with self.db.cursor() as cur:
            cur.execute("SELECT id, name, parent_tag_id FROM tag ORDER BY id")
            rows = cur.fetchall()

        # 全ノードを構築し、親子リンクを張る
        nodes: dict[int, TagNode] = {
            r[0]: TagNode(id=r[0], name=r[1], parent_tag_id=r[2]) for r in rows
        }
        children_of: dict[Optional[int], List[TagNode]] = {}
        for node in nodes.values():
            children_of.setdefault(node.parent_tag_id, []).append(node)

        def attach(node: TagNode) -> TagNode:
            node.children = [attach(c) for c in children_of.get(node.id, [])]
            return node

        roots = children_of.get(parent_tag_id, [])
        return [attach(n) for n in roots]

    def _get(self, cur, tag_id: int) -> Optional[TagNode]:
        cur.execute(
            "SELECT id, name, parent_tag_id FROM tag WHERE id = %s", (tag_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return TagNode(id=row[0], name=row[1], parent_tag_id=row[2])

    # ------------------------------------------------------------------ #
    # 更新系
    # ------------------------------------------------------------------ #
    def create_tag(self, name: str, parent_tag_id: Optional[int] = None) -> TagNode:
        with self.db.cursor() as cur:
            if parent_tag_id is not None:
                if self._get(cur, parent_tag_id) is None:
                    raise TagError(f"parent tag id={parent_tag_id} does not exist")
            # 重複チェック（UNIQUE制約を明示的に業務エラー化）
            cur.execute("SELECT 1 FROM tag WHERE name = %s", (name,))
            if cur.fetchone() is not None:
                raise TagError(f"tag name '{name}' already exists")

            cur.execute(
                "INSERT INTO tag (name, parent_tag_id) VALUES (%s, %s) RETURNING id",
                (name, parent_tag_id),
            )
            new_id = cur.fetchone()[0]
        return TagNode(id=new_id, name=name, parent_tag_id=parent_tag_id)

    def rename_tag(self, tag_id: int, new_name: str) -> TagNode:
        with self.db.cursor() as cur:
            node = self._get(cur, tag_id)
            if node is None:
                raise TagError(f"tag id={tag_id} does not exist")
            cur.execute(
                "SELECT 1 FROM tag WHERE name = %s AND id <> %s", (new_name, tag_id)
            )
            if cur.fetchone() is not None:
                raise TagError(f"tag name '{new_name}' already exists")
            cur.execute("UPDATE tag SET name = %s WHERE id = %s", (new_name, tag_id))
        return TagNode(id=tag_id, name=new_name, parent_tag_id=node.parent_tag_id)

    def move_tag(self, tag_id: int, new_parent_tag_id: Optional[int]) -> TagNode:
        with self.db.cursor() as cur:
            node = self._get(cur, tag_id)
            if node is None:
                raise TagError(f"tag id={tag_id} does not exist")
            if new_parent_tag_id is not None:
                if self._get(cur, new_parent_tag_id) is None:
                    raise TagError(f"parent tag id={new_parent_tag_id} does not exist")
                self._assert_no_cycle(cur, tag_id, new_parent_tag_id)
            cur.execute(
                "UPDATE tag SET parent_tag_id = %s WHERE id = %s",
                (new_parent_tag_id, tag_id),
            )
        return TagNode(id=tag_id, name=node.name, parent_tag_id=new_parent_tag_id)

    def delete_tag(self, tag_id: int) -> None:
        with self.db.cursor() as cur:
            if self._get(cur, tag_id) is None:
                raise TagError(f"tag id={tag_id} does not exist")
            # qa_tag からの参照がある場合は拒否
            cur.execute("SELECT 1 FROM qa_tag WHERE tag_id = %s LIMIT 1", (tag_id,))
            if cur.fetchone() is not None:
                raise TagError(
                    f"tag id={tag_id} is referenced by qa_tag; cannot delete"
                )
            # 子タグを持つ場合は拒否
            cur.execute(
                "SELECT 1 FROM tag WHERE parent_tag_id = %s LIMIT 1", (tag_id,)
            )
            if cur.fetchone() is not None:
                raise TagError(f"tag id={tag_id} has child tags; cannot delete")
            cur.execute("DELETE FROM tag WHERE id = %s", (tag_id,))

    # ------------------------------------------------------------------ #
    # 循環参照防止（実装指示書 T18 / 5.6）
    # ------------------------------------------------------------------ #
    @staticmethod
    def _assert_no_cycle(cur, tag_id: int, new_parent_tag_id: int) -> None:
        """new_parent_tag_id が tag_id 自身、またはその子孫でないことを検証する。

        new_parent_tag_id から parent_tag_id を再帰的に辿り（＝祖先集合）、
        その中に tag_id が含まれる（＝tag_id は new_parent の祖先）場合、
        tag_id を new_parent の下へ移すと循環になるため拒否する。
        """
        if new_parent_tag_id == tag_id:
            raise TagError("a tag cannot be its own parent (cycle)")

        cur.execute(
            """
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_tag_id FROM tag WHERE id = %s
                UNION ALL
                SELECT t.id, t.parent_tag_id
                FROM tag t
                JOIN ancestors a ON t.id = a.parent_tag_id
            )
            SELECT 1 FROM ancestors WHERE id = %s LIMIT 1
            """,
            (new_parent_tag_id, tag_id),
        )
        if cur.fetchone() is not None:
            raise TagError(
                "moving this tag under the given parent would create a cycle"
            )
