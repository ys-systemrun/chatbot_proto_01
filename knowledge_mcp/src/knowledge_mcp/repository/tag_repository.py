"""TagRepository（実装指示書 5.6 / ADR-0006、IMPL-202608060837 4.3 で description/alias 拡張）。

tag / qa_tag / tag_alias テーブルへの CRUD を提供する。
**内部状態としてタグ情報をキャッシュしてはならない**（呼び出しの都度SQLでDBを参照する）。
外部から tag テーブルが直接変更された場合でも、再起動なしに最新内容を返すため。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..db.connection import Database
from ..models.tag import TagNode

# 表示順序（display_order）の新規採番・末尾追加・「1つ下へ」で用いる固定間隔（ADR-0074 決定3）。
# 初期値・末尾追加はこの間隔で採番し、間の挿入は前後2値の中間値を取る（範囲UPDATEを避ける）。
_DISPLAY_ORDER_GAP = 1000.0


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
        description / aliases も併せて取得する。
        """
        with self.db.cursor() as cur:
            # 兄弟集合内は display_order 昇順（同値時は id をタイブレーク, ADR-0074 決定4）。
            # グルーピングは行の出現順を保持するため、この並びで各階層の兄弟順が正しく決まる。
            cur.execute(
                "SELECT id, name, parent_tag_id, description, folder_id, display_order"
                " FROM tag ORDER BY display_order, id"
            )
            rows = cur.fetchall()
            aliases_by_tag = self._load_aliases(cur)

        # 全ノードを構築し、親子リンクを張る
        nodes: Dict[int, TagNode] = {
            r[0]: TagNode(
                id=r[0],
                name=r[1],
                parent_tag_id=r[2],
                description=r[3],
                folder_id=r[4],
                display_order=r[5],
                aliases=aliases_by_tag.get(r[0], []),
            )
            for r in rows
        }
        children_of: Dict[Optional[int], List[TagNode]] = {}
        for node in nodes.values():
            children_of.setdefault(node.parent_tag_id, []).append(node)

        def attach(node: TagNode) -> TagNode:
            node.children = [attach(c) for c in children_of.get(node.id, [])]
            return node

        roots = children_of.get(parent_tag_id, [])
        return [attach(n) for n in roots]

    @staticmethod
    def _load_aliases(cur) -> Dict[int, List[dict]]:
        """tag_alias を全件読み込み、tag_id -> [{"id", "alias"}, ...] の辞書を返す。"""
        cur.execute("SELECT id, tag_id, alias FROM tag_alias ORDER BY id")
        result: Dict[int, List[dict]] = {}
        for row in cur.fetchall():
            result.setdefault(row[1], []).append({"id": row[0], "alias": row[2]})
        return result

    def _get_node(self, cur, tag_id: int) -> Optional[TagNode]:
        """単一タグを description / folder_id / aliases 込みで取得する（children は空）。"""
        cur.execute(
            "SELECT id, name, parent_tag_id, description, folder_id, display_order"
            " FROM tag WHERE id = %s",
            (tag_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cur.execute(
            "SELECT id, alias FROM tag_alias WHERE tag_id = %s ORDER BY id", (tag_id,)
        )
        aliases = [{"id": r[0], "alias": r[1]} for r in cur.fetchall()]
        return TagNode(
            id=row[0],
            name=row[1],
            parent_tag_id=row[2],
            description=row[3],
            folder_id=row[4],
            display_order=row[5],
            aliases=aliases,
        )

    def _exists(self, cur, tag_id: int) -> bool:
        cur.execute("SELECT 1 FROM tag WHERE id = %s", (tag_id,))
        return cur.fetchone() is not None

    def _folder_exists(self, cur, folder_id: int) -> bool:
        cur.execute("SELECT 1 FROM tag_folder WHERE id = %s", (folder_id,))
        return cur.fetchone() is not None

    # ------------------------------------------------------------------ #
    # display_order（表示順序）ヘルパ（ADR-0074）
    # table / parent_col は内部リテラルのみで組み立てる（外部入力を混ぜない）。
    # parent_id が NULL（ルート）と非NULLで SQL を分岐する（"= NULL" は常に偽になるため）。
    # ------------------------------------------------------------------ #
    @staticmethod
    def _next_display_order(cur, table: str, parent_col: str, parent_id: Optional[int]) -> float:
        """兄弟集合の末尾に追加するための display_order を返す（最大値 + GAP、空集合なら GAP）。"""
        if parent_id is None:
            cur.execute(
                f"SELECT MAX(display_order) FROM {table} WHERE {parent_col} IS NULL"
            )
        else:
            cur.execute(
                f"SELECT MAX(display_order) FROM {table} WHERE {parent_col} = %s",
                (parent_id,),
            )
        row = cur.fetchone()
        current_max = row[0] if row else None
        if current_max is None:
            return _DISPLAY_ORDER_GAP
        return current_max + _DISPLAY_ORDER_GAP

    @staticmethod
    def _ordered_siblings(cur, table: str, parent_col: str, parent_id: Optional[int]):
        """兄弟集合を display_order, id 昇順で [(id, display_order), ...] として返す。"""
        if parent_id is None:
            cur.execute(
                f"SELECT id, display_order FROM {table}"
                f" WHERE {parent_col} IS NULL ORDER BY display_order, id"
            )
        else:
            cur.execute(
                f"SELECT id, display_order FROM {table}"
                f" WHERE {parent_col} = %s ORDER BY display_order, id",
                (parent_id,),
            )
        return cur.fetchall()

    @staticmethod
    def _compute_reordered_value(siblings, target_id: int, direction: str) -> Optional[float]:
        """並べ替え後の display_order を中間値挿入方式で計算する（ADR-0074 決定3）。

        siblings は display_order, id 昇順の [(id, display_order), ...]。
        境界（先頭で up／末尾で down）では None を返す（No-Op、UPDATE しない）。
        """
        ids = [s[0] for s in siblings]
        orders = [s[1] for s in siblings]
        idx = ids.index(target_id)
        if direction == "up":
            if idx == 0:
                return None  # 既に先頭（No-Op）
            b = orders[idx - 1]
            a = orders[idx - 2] if idx - 2 >= 0 else None
            return (a + b) / 2 if a is not None else b / 2
        else:  # "down"
            if idx == len(ids) - 1:
                return None  # 既に末尾（No-Op）
            c = orders[idx + 1]
            d = orders[idx + 2] if idx + 2 < len(orders) else None
            return (c + d) / 2 if d is not None else c + _DISPLAY_ORDER_GAP

    def find_by_name(self, name: str) -> Optional[TagNode]:
        """タグ名で1件検索する（存在しなければ None）。

        create_tag の重複チェック（WHERE name = %s）と同一条件。QA一括インポート
        （IMPL-202608261022 T9 / ADR-0053）が、未知タグを自動作成する前の存在確認に使う。
        """
        with self.db.cursor() as cur:
            cur.execute("SELECT id FROM tag WHERE name = %s", (name,))
            row = cur.fetchone()
            if row is None:
                return None
            return self._get_node(cur, row[0])

    # ------------------------------------------------------------------ #
    # CSV エクスポート（IMPL-202608281500 T1 / ADR-0065）
    # ------------------------------------------------------------------ #
    def export_tags(self) -> List[dict]:
        """全タグを {id, name, parent_name, description, aliases} のフラットな配列で返す。

        既存 list_tags() が構築するツリーをそのまま深さ優先で走査し、各ノードの
        親ノードの name を parent_name として持ち回る（ルート直下は parent_name=None）。
        親タグが子タグより先に出現する階層順で返す（ADR-0065 決定5）。
        aliases は当該タグのエイリアス文字列の配列（ADR-0081 でエクスポート対象に追加。
        CSV では web_backend 側でパイプ区切りに整形する）。children は含めない。
        新規 SQL は発行せず、list_tags() の1クエリのみを再利用する。
        """
        result: List[dict] = []

        def walk(node: TagNode, parent_name: Optional[str]) -> None:
            result.append(
                {
                    "id": node.id,
                    "name": node.name,
                    "parent_name": parent_name,
                    "description": node.description,
                    "aliases": [a["alias"] for a in node.aliases],
                }
            )
            for child in node.children:
                walk(child, node.name)

        for root in self.list_tags():
            walk(root, None)
        return result

    # ------------------------------------------------------------------ #
    # 更新系
    # ------------------------------------------------------------------ #
    def create_tag(
        self,
        name: str,
        parent_tag_id: Optional[int] = None,
        description: Optional[str] = None,
        folder_id: Optional[int] = None,
    ) -> TagNode:
        with self.db.cursor() as cur:
            if parent_tag_id is not None and not self._exists(cur, parent_tag_id):
                raise TagError(f"parent tag id={parent_tag_id} does not exist")
            if folder_id is not None and not self._folder_exists(cur, folder_id):
                raise TagError(f"tag folder id={folder_id} does not exist")
            # 重複チェック（UNIQUE制約を明示的に業務エラー化）
            cur.execute("SELECT 1 FROM tag WHERE name = %s", (name,))
            if cur.fetchone() is not None:
                raise TagError(f"tag name '{name}' already exists")

            # 新規タグは兄弟集合（同じ parent_tag_id）の末尾へ採番する（ADR-0074 決定3）。
            display_order = self._next_display_order(
                cur, "tag", "parent_tag_id", parent_tag_id
            )
            cur.execute(
                "INSERT INTO tag"
                " (name, parent_tag_id, description, folder_id, display_order)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (name, parent_tag_id, description, folder_id, display_order),
            )
            new_id = cur.fetchone()[0]
            node = self._get_node(cur, new_id)
        return node

    def set_tag_folder(self, tag_id: int, folder_id: Optional[int]) -> TagNode:
        """タグにタグフォルダを付与・変更・解除する（folder_id=None で解除, ADR-0072）。"""
        with self.db.cursor() as cur:
            if not self._exists(cur, tag_id):
                raise TagError(f"tag id={tag_id} does not exist")
            if folder_id is not None and not self._folder_exists(cur, folder_id):
                raise TagError(f"tag folder id={folder_id} does not exist")
            cur.execute(
                "UPDATE tag SET folder_id = %s WHERE id = %s", (folder_id, tag_id)
            )
            node = self._get_node(cur, tag_id)
        return node

    # ------------------------------------------------------------------ #
    # タグフォルダマスタ CRUD（ADR-0072 で新設、ADR-0073 で階層化）
    # tag_alias と同様の「独立したマスタテーブル＋外部キー」方式に、
    # 自己参照 parent_folder_id によるツリー構造を加えたもの。
    # folder は分類表示専用であり search_knowledge の検索には一切関与しない。
    # フォルダ名（name）は表示用ラベルであり一意性を持たない（id で識別, ADR-0073 決定1）。
    # ------------------------------------------------------------------ #
    def list_tag_folders(self) -> List[dict]:
        """タグフォルダを木構造で返す（ADR-0073）。

        各ノードは {"id", "name", "description", "parent_folder_id", "children": [...]}。
        parent_folder_id が NULL のフォルダをルートとし、子孫を children にネストする。
        毎回テーブル全体を1クエリで読み直す（キャッシュしない）。
        """
        with self.db.cursor() as cur:
            # 兄弟集合内は display_order 昇順（同値時は id をタイブレーク, ADR-0074 決定4）。
            cur.execute(
                "SELECT id, name, description, parent_folder_id, display_order"
                " FROM tag_folder ORDER BY display_order, id"
            )
            rows = cur.fetchall()

        nodes: Dict[int, dict] = {
            r[0]: {
                "id": r[0],
                "name": r[1],
                "description": r[2],
                "parent_folder_id": r[3],
                "display_order": r[4],
                "children": [],
            }
            for r in rows
        }
        children_of: Dict[Optional[int], List[dict]] = {}
        for node in nodes.values():
            children_of.setdefault(node["parent_folder_id"], []).append(node)

        def attach(node: dict) -> dict:
            node["children"] = [attach(c) for c in children_of.get(node["id"], [])]
            return node

        roots = children_of.get(None, [])
        return [attach(n) for n in roots]

    def create_tag_folder(
        self,
        name: str,
        description: Optional[str] = None,
        parent_folder_id: Optional[int] = None,
    ) -> dict:
        """タグフォルダを新規作成する（ADR-0073）。

        parent_folder_id 指定時は当該フォルダの存在を検証する。
        同名フォルダの存在チェック（作成拒否）は行わない（ADR-0073 決定1: name は重複可）。
        """
        with self.db.cursor() as cur:
            if parent_folder_id is not None and not self._folder_exists(
                cur, parent_folder_id
            ):
                raise TagError(
                    f"parent tag folder id={parent_folder_id} does not exist"
                )
            # 新規フォルダは兄弟集合（同じ parent_folder_id）の末尾へ採番する（ADR-0074 決定3）。
            display_order = self._next_display_order(
                cur, "tag_folder", "parent_folder_id", parent_folder_id
            )
            cur.execute(
                "INSERT INTO tag_folder"
                " (name, description, parent_folder_id, display_order)"
                " VALUES (%s, %s, %s, %s) RETURNING id",
                (name, description, parent_folder_id, display_order),
            )
            new_id = cur.fetchone()[0]
        return {
            "id": new_id,
            "name": name,
            "description": description,
            "parent_folder_id": parent_folder_id,
            "display_order": display_order,
            "children": [],
        }

    def rename_tag_folder(
        self, folder_id: int, new_name: str, description: Optional[str] = None
    ) -> dict:
        """タグフォルダの名称・説明文を変更する。description=None は変更しない（維持）。

        同名フォルダの存在チェック（改名拒否）は行わない（ADR-0073 決定1: name は重複可）。
        """
        with self.db.cursor() as cur:
            if not self._folder_exists(cur, folder_id):
                raise TagError(f"tag folder id={folder_id} does not exist")
            if description is not None:
                cur.execute(
                    "UPDATE tag_folder SET name = %s, description = %s WHERE id = %s",
                    (new_name, description, folder_id),
                )
            else:
                cur.execute(
                    "UPDATE tag_folder SET name = %s WHERE id = %s",
                    (new_name, folder_id),
                )
            cur.execute(
                "SELECT id, name, description, parent_folder_id, display_order"
                " FROM tag_folder WHERE id = %s",
                (folder_id,),
            )
            r = cur.fetchone()
        return {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "parent_folder_id": r[3],
            "display_order": r[4],
        }

    def move_tag_folder(
        self, folder_id: int, new_parent_folder_id: Optional[int]
    ) -> dict:
        """タグフォルダの親（parent_folder_id）を変更する（ADR-0073 決定4）。

        move_tag と同じ考え方で、new_parent_folder_id が folder_id 自身または
        その子孫である場合は循環参照として拒否する。new_parent_folder_id=None で
        ルートフォルダへ移動する。
        """
        with self.db.cursor() as cur:
            if not self._folder_exists(cur, folder_id):
                raise TagError(f"tag folder id={folder_id} does not exist")
            if new_parent_folder_id is not None:
                if not self._folder_exists(cur, new_parent_folder_id):
                    raise TagError(
                        f"parent tag folder id={new_parent_folder_id} does not exist"
                    )
                self._assert_no_folder_cycle(cur, folder_id, new_parent_folder_id)
            # reparent 後は位置指定手段が無いため、新しい兄弟集合の末尾へ display_order を
            # 再設定する（ADR-0074 決定3）。末尾値は付け替え前の対象親集合の最大値 + GAP で
            # 計算する（付け替え後だと移動ノード自身の旧値が混入するため）。
            new_order = self._next_display_order(
                cur, "tag_folder", "parent_folder_id", new_parent_folder_id
            )
            cur.execute(
                "UPDATE tag_folder"
                " SET parent_folder_id = %s, display_order = %s WHERE id = %s",
                (new_parent_folder_id, new_order, folder_id),
            )
            cur.execute(
                "SELECT id, name, description, parent_folder_id, display_order"
                " FROM tag_folder WHERE id = %s",
                (folder_id,),
            )
            r = cur.fetchone()
        return {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "parent_folder_id": r[3],
            "display_order": r[4],
        }

    def reorder_tag_folder(self, folder_id: int, direction: str) -> dict:
        """タグフォルダを兄弟集合内で1つ上／下へ移動する（ADR-0074 決定2/3）。

        direction は "up" | "down"。境界（先頭で up／末尾で down）は No-Op（更新しない）。
        更新対象は移動フォルダ1件のみ（中間値挿入）。更新後のフォルダ dict を返す。
        """
        if direction not in ("up", "down"):
            raise TagError(f"invalid direction: {direction!r} (expected 'up' or 'down')")
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT parent_folder_id FROM tag_folder WHERE id = %s",
                (folder_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise TagError(f"tag folder id={folder_id} does not exist")
            parent_folder_id = row[0]
            siblings = self._ordered_siblings(
                cur, "tag_folder", "parent_folder_id", parent_folder_id
            )
            new_order = self._compute_reordered_value(siblings, folder_id, direction)
            if new_order is not None:
                cur.execute(
                    "UPDATE tag_folder SET display_order = %s WHERE id = %s",
                    (new_order, folder_id),
                )
            cur.execute(
                "SELECT id, name, description, parent_folder_id, display_order"
                " FROM tag_folder WHERE id = %s",
                (folder_id,),
            )
            r = cur.fetchone()
        return {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "parent_folder_id": r[3],
            "display_order": r[4],
        }

    def delete_tag_folder(self, folder_id: int) -> None:
        """タグフォルダを削除する（ADR-0073 決定3）。

        - tag から参照されている場合は削除を拒否する（ADR-0072 の判断を継続）。
        - 削除対象が子フォルダを持つ場合、それらの子フォルダの parent_folder_id を
          削除対象の親（祖父母フォルダ。ルートだった場合は NULL）へ繰り上げてから削除する。
          子フォルダに割り当てられたタグの folder_id は変化しない。
        """
        with self.db.cursor() as cur:
            if not self._folder_exists(cur, folder_id):
                raise TagError(f"tag folder id={folder_id} does not exist")
            cur.execute(
                "SELECT 1 FROM tag WHERE folder_id = %s LIMIT 1", (folder_id,)
            )
            if cur.fetchone() is not None:
                raise TagError(
                    f"tag folder id={folder_id} is referenced by tags; cannot delete"
                )
            # 子フォルダを削除対象の親（祖父母フォルダ）へ繰り上げる。
            cur.execute(
                """
                UPDATE tag_folder
                SET parent_folder_id = (
                    SELECT parent_folder_id FROM tag_folder WHERE id = %s
                )
                WHERE parent_folder_id = %s
                """,
                (folder_id, folder_id),
            )
            cur.execute("DELETE FROM tag_folder WHERE id = %s", (folder_id,))

    def rename_tag(
        self,
        tag_id: int,
        new_name: str,
        description: Optional[str] = None,
    ) -> TagNode:
        with self.db.cursor() as cur:
            if not self._exists(cur, tag_id):
                raise TagError(f"tag id={tag_id} does not exist")
            cur.execute(
                "SELECT 1 FROM tag WHERE name = %s AND id <> %s", (new_name, tag_id)
            )
            if cur.fetchone() is not None:
                raise TagError(f"tag name '{new_name}' already exists")
            if description is not None:
                cur.execute(
                    "UPDATE tag SET name = %s, description = %s WHERE id = %s",
                    (new_name, description, tag_id),
                )
            else:
                cur.execute(
                    "UPDATE tag SET name = %s WHERE id = %s", (new_name, tag_id)
                )
            node = self._get_node(cur, tag_id)
        return node

    def set_tag_description(
        self, tag_id: int, description: Optional[str]
    ) -> TagNode:
        with self.db.cursor() as cur:
            if not self._exists(cur, tag_id):
                raise TagError(f"tag id={tag_id} does not exist")
            cur.execute(
                "UPDATE tag SET description = %s WHERE id = %s", (description, tag_id)
            )
            node = self._get_node(cur, tag_id)
        return node

    def add_tag_alias(self, tag_id: int, alias: str) -> dict:
        """{"id": int, "tag_id": int, "alias": str} を返す。alias重複はTagErrorとする。"""
        with self.db.cursor() as cur:
            if not self._exists(cur, tag_id):
                raise TagError(f"tag id={tag_id} does not exist")
            cur.execute("SELECT 1 FROM tag_alias WHERE alias = %s", (alias,))
            if cur.fetchone() is not None:
                raise TagError(f"alias '{alias}' already exists")
            cur.execute(
                "INSERT INTO tag_alias (tag_id, alias) VALUES (%s, %s) RETURNING id",
                (tag_id, alias),
            )
            new_id = cur.fetchone()[0]
        return {"id": new_id, "tag_id": tag_id, "alias": alias}

    def update_tag_alias(self, alias_id: int, new_alias: str) -> dict:
        """対象エイリアスの文字列を書き換える（ADR-0080）。{"id", "tag_id", "alias"} を返す。

        alias_id の存在チェックと、new_alias が自分自身以外の既存エイリアスと重複していないか
        （add_tag_alias と同じ tag_alias.alias の UNIQUE 制約由来の TagError）を確認したうえで
        UPDATE する。tag_id の付け替え（別タグへの移動）は行わない。
        """
        with self.db.cursor() as cur:
            cur.execute("SELECT tag_id FROM tag_alias WHERE id = %s", (alias_id,))
            row = cur.fetchone()
            if row is None:
                raise TagError(f"alias id={alias_id} does not exist")
            tag_id = row[0]
            cur.execute(
                "SELECT 1 FROM tag_alias WHERE alias = %s AND id <> %s",
                (new_alias, alias_id),
            )
            if cur.fetchone() is not None:
                raise TagError(f"alias '{new_alias}' already exists")
            cur.execute(
                "UPDATE tag_alias SET alias = %s WHERE id = %s", (new_alias, alias_id)
            )
        return {"id": alias_id, "tag_id": tag_id, "alias": new_alias}

    def remove_tag_alias(self, alias_id: int) -> None:
        with self.db.cursor() as cur:
            cur.execute("SELECT 1 FROM tag_alias WHERE id = %s", (alias_id,))
            if cur.fetchone() is None:
                raise TagError(f"alias id={alias_id} does not exist")
            cur.execute("DELETE FROM tag_alias WHERE id = %s", (alias_id,))

    def move_tag(self, tag_id: int, new_parent_tag_id: Optional[int]) -> TagNode:
        with self.db.cursor() as cur:
            if not self._exists(cur, tag_id):
                raise TagError(f"tag id={tag_id} does not exist")
            if new_parent_tag_id is not None:
                if not self._exists(cur, new_parent_tag_id):
                    raise TagError(f"parent tag id={new_parent_tag_id} does not exist")
                self._assert_no_cycle(cur, tag_id, new_parent_tag_id)
            # reparent 後は新しい兄弟集合の末尾へ display_order を再設定する（ADR-0074 決定3）。
            # 末尾値は付け替え前の対象親集合の最大値 + GAP で計算する。
            new_order = self._next_display_order(
                cur, "tag", "parent_tag_id", new_parent_tag_id
            )
            cur.execute(
                "UPDATE tag SET parent_tag_id = %s, display_order = %s WHERE id = %s",
                (new_parent_tag_id, new_order, tag_id),
            )
            node = self._get_node(cur, tag_id)
        return node

    def reorder_tag(self, tag_id: int, direction: str) -> TagNode:
        """タグを兄弟集合内で1つ上／下へ移動する（ADR-0074 決定2/3）。

        direction は "up" | "down"。境界（先頭で up／末尾で down）は No-Op（更新しない）。
        更新対象は移動タグ1件のみ（中間値挿入）。更新後の TagNode を返す。
        """
        if direction not in ("up", "down"):
            raise TagError(f"invalid direction: {direction!r} (expected 'up' or 'down')")
        with self.db.cursor() as cur:
            node = self._get_node(cur, tag_id)
            if node is None:
                raise TagError(f"tag id={tag_id} does not exist")
            siblings = self._ordered_siblings(
                cur, "tag", "parent_tag_id", node.parent_tag_id
            )
            new_order = self._compute_reordered_value(siblings, tag_id, direction)
            if new_order is not None:
                cur.execute(
                    "UPDATE tag SET display_order = %s WHERE id = %s",
                    (new_order, tag_id),
                )
            node = self._get_node(cur, tag_id)
        return node

    def delete_tag(self, tag_id: int) -> None:
        with self.db.cursor() as cur:
            if not self._exists(cur, tag_id):
                raise TagError(f"tag id={tag_id} does not exist")
            # qa_tag からの参照がある場合は拒否
            cur.execute("SELECT 1 FROM hiroba_qa_tag WHERE tag_id = %s LIMIT 1", (tag_id,))
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
            # 拒否判定を通過したら、紐づく tag_alias を先にカスケード削除する
            # （IMPL-202608060837 0節の決定）。
            cur.execute("DELETE FROM tag_alias WHERE tag_id = %s", (tag_id,))
            cur.execute("DELETE FROM tag WHERE id = %s", (tag_id,))

    # ------------------------------------------------------------------ #
    # 一括インポート（IMPL-202608261630 T1 / ADR-0061）
    # ------------------------------------------------------------------ #
    def _import_aliases_for_tag(self, tag_id: int, aliases: List[str]) -> List[str]:
        """CSV由来のエイリアス列を対象タグへ「追加専用」で登録する（ADR-0081 決定2/3）。

        - 対象タグに未登録のエイリアスのみ INSERT する。
        - 既に対象タグ自身に登録済みのものは何もしない（追加専用のため冪等）。
        - 別タグに登録済み（tag_alias.alias の UNIQUE 制約に抵触）のものは、その1件のみを
          警告として扱い（登録はスキップ）、警告メッセージの配列に積んで返す。他のエイリアス・
          タグ本体の処理は止めない（行内のエイリアス単位でのエラー許容）。
        CSV から省かれた既存エイリアスの削除は行わない（非破壊）。
        """
        warnings: List[str] = []
        for raw in aliases:
            alias = (raw or "").strip()
            if not alias:
                continue
            with self.db.cursor() as cur:
                cur.execute("SELECT tag_id FROM tag_alias WHERE alias = %s", (alias,))
                row = cur.fetchone()
                if row is not None:
                    if row[0] != tag_id:
                        warnings.append(
                            f"alias '{alias}' already belongs to another tag"
                        )
                    # 対象タグ自身に既存 → 追加専用のため何もしない
                    continue
                cur.execute(
                    "INSERT INTO tag_alias (tag_id, alias) VALUES (%s, %s)",
                    (tag_id, alias),
                )
        return warnings

    def import_tag_batch(self, rows: List[dict]) -> List[dict]:
        """CSVの各行（dict: name, parent_name, description, aliases）をまとめて登録・更新する。

        - `name`が既存タグと一致すれば更新（0節: parent_name/descriptionが空欄なら変更なし）、
          一致しなければ新規作成する（0節: parent_name空欄はルート直下）。
        - `parent_name`は、既存タグまたは同一CSV内の他行のnameで解決する。CSV内の行の並び順には
          依存しない（複数パスによる反復解決、ADR-0061）。
        - `aliases`（文字列配列, 任意）は対象タグへ追加専用で登録する（ADR-0081）。別タグに既存の
          エイリアスはその1件のみ警告とし（`alias_warnings`）、行の処理は継続する。
        - 循環参照は既存のcreate_tag/move_tagのバリデーションで検出する。
        - 戻り値: [{"row": <行番号>, "status": "success"|"error", "tag_id": ..., "error": ...,
          "alias_warnings": [...]（別タグ既存エイリアス等がある場合のみ）}, ...]
        """
        results: List[Optional[dict]] = [None] * len(rows)

        with self.db.cursor() as cur:
            cur.execute("SELECT name, id FROM tag")
            resolved_names: Dict[str, int] = {name: tid for name, tid in cur.fetchall()}

        remaining = list(range(len(rows)))
        progress = True
        while remaining and progress:
            progress = False
            still_remaining = []
            for i in remaining:
                row = rows[i]
                name = (row.get("name") or "").strip()
                parent_name = (row.get("parent_name") or "").strip()
                description = (row.get("description") or "").strip() or None

                if not name:
                    results[i] = {"row": i, "status": "error", "error": "name is required"}
                    progress = True
                    continue

                # parent_name が指定されていて、まだ解決できていない場合は次パスへ繰り越す
                if parent_name and parent_name not in resolved_names:
                    still_remaining.append(i)
                    continue

                parent_tag_id = resolved_names.get(parent_name) if parent_name else None

                try:
                    if name in resolved_names:
                        # 既存（またはこのバッチ内で作成済み）タグの更新
                        tag_id = resolved_names[name]
                        if parent_name:  # 空欄=変更なし（0節）
                            self.move_tag(tag_id, parent_tag_id)
                        if description is not None:  # 空欄=変更なし
                            self.set_tag_description(tag_id, description)
                    else:
                        node = self.create_tag(
                            name=name, parent_tag_id=parent_tag_id, description=description
                        )
                        tag_id = node.id
                        resolved_names[name] = tag_id
                    # エイリアスは追加専用で登録する（ADR-0081）。別タグ既存分は警告に積む。
                    alias_warnings = self._import_aliases_for_tag(
                        tag_id, row.get("aliases") or []
                    )
                    result = {"row": i, "status": "success", "tag_id": tag_id}
                    if alias_warnings:
                        result["alias_warnings"] = alias_warnings
                    results[i] = result
                except TagError as e:
                    results[i] = {"row": i, "status": "error", "error": str(e)}
                progress = True

            remaining = still_remaining

        # 反復終了後も残っている行 = parent_name が既存タグにもCSV内の他行にも見つからない
        for i in remaining:
            parent_name = (rows[i].get("parent_name") or "").strip()
            results[i] = {
                "row": i,
                "status": "error",
                "error": f"parent tag '{parent_name}' not found (neither in existing tags nor in this CSV)",
            }

        return results

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

    @staticmethod
    def _assert_no_folder_cycle(
        cur, folder_id: int, new_parent_folder_id: int
    ) -> None:
        """タグフォルダ版の循環参照検証（ADR-0073 決定4、_assert_no_cycle のフォルダ版）。

        new_parent_folder_id から parent_folder_id を再帰的に辿り（＝祖先集合）、
        その中に folder_id が含まれる（＝folder_id は new_parent の祖先）場合、
        folder_id を new_parent の下へ移すと循環になるため拒否する。
        """
        if new_parent_folder_id == folder_id:
            raise TagError("a tag folder cannot be its own parent (cycle)")

        cur.execute(
            """
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_folder_id FROM tag_folder WHERE id = %s
                UNION ALL
                SELECT f.id, f.parent_folder_id
                FROM tag_folder f
                JOIN ancestors a ON f.id = a.parent_folder_id
            )
            SELECT 1 FROM ancestors WHERE id = %s LIMIT 1
            """,
            (new_parent_folder_id, folder_id),
        )
        if cur.fetchone() is not None:
            raise TagError(
                "moving this tag folder under the given parent would create a cycle"
            )
