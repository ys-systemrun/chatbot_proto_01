"""タグ管理ツール／search_knowledge の単体テスト（実装指示書 9.1, 9.4 / IMPL-202608060837 8.1）。

タグ操作のロジック（create/rename/move/delete/list + 循環参照防止 + description/alias）は、
TagRepository を DB非依存のインメモリ Fake DB で検証する（MCPツールは薄いラッパのため）。
search_knowledge の min_score フィルタと ToolError 変換は、FastMCP が利用可能な場合のみ検証する。
"""

import os
import sys
from contextlib import contextmanager

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from knowledge_mcp.repository.tag_repository import TagRepository, TagError


# --------------------------------------------------------------------------- #
# インメモリ Fake DB（TagRepository が発行するSQLを部分一致で解釈する）
# --------------------------------------------------------------------------- #
class FakeCursor:
    def __init__(self, store):
        self.s = store
        self._result = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        q = " ".join(sql.split())
        p = params or ()
        self._result = []

        # --- 書き込み系（SELECT の部分一致に横取りされないよう先に判定） --- #
        # タグフォルダ（hiroba_tag_folder）は hiroba_tag のプレフィックスに一致するため先に判定する。
        if q.startswith("INSERT INTO hiroba_tag_folder"):
            new_id = self.s["next_folder_id"]
            self.s["next_folder_id"] += 1
            self.s["folders"][new_id] = {
                "name": p[0],
                "description": p[1],
                "parent": p[2] if len(p) > 2 else None,
                # display_order は INSERT の第4パラメータ（ADR-0074）。
                "order": p[3] if len(p) > 3 else None,
            }
            self._result = [(new_id,)]
            return
        if q.startswith("UPDATE hiroba_tag_folder SET name"):
            if "description" in q:
                name, description, fid = p
                self.s["folders"][fid]["name"] = name
                self.s["folders"][fid]["description"] = description
            else:
                name, fid = p
                self.s["folders"][fid]["name"] = name
            return
        if q.startswith("UPDATE hiroba_tag_folder SET parent_folder_id"):
            # 繰り上げ（子フォルダを削除対象の親へ）と、単純な移動の2種類がある（ADR-0073）。
            # 移動時は display_order も同時更新する（ADR-0074、末尾へ再採番）。
            if "SELECT parent_folder_id" in q:
                deleted_id = p[0]
                grandparent = self.s["folders"].get(deleted_id, {}).get("parent")
                for f in self.s["folders"].values():
                    if f.get("parent") == deleted_id:
                        f["parent"] = grandparent
            else:
                new_parent, new_order, fid = p
                self.s["folders"][fid]["parent"] = new_parent
                self.s["folders"][fid]["order"] = new_order
            return
        if q.startswith("UPDATE hiroba_tag_folder SET display_order"):
            new_order, fid = p
            self.s["folders"][fid]["order"] = new_order
            return
        if q.startswith("DELETE FROM hiroba_tag_folder"):
            self.s["folders"].pop(p[0], None)
            return
        if q.startswith("INSERT INTO hiroba_tag_alias"):
            new_id = self.s["next_alias_id"]
            self.s["next_alias_id"] += 1
            self.s["aliases"][new_id] = {"tag_id": p[0], "alias": p[1]}
            self._result = [(new_id,)]
            return
        if q.startswith("INSERT INTO hiroba_tag"):
            new_id = self.s["next_tag_id"]
            self.s["next_tag_id"] += 1
            self.s["tags"][new_id] = {
                "name": p[0],
                "parent": p[1],
                "description": p[2] if len(p) > 2 else None,
                "folder": p[3] if len(p) > 3 else None,
                # display_order は INSERT の第5パラメータ（ADR-0074）。
                "order": p[4] if len(p) > 4 else None,
            }
            self._result = [(new_id,)]
            return
        if q.startswith("UPDATE hiroba_tag SET name"):
            if "description" in q:
                name, description, tid = p
                self.s["tags"][tid]["name"] = name
                self.s["tags"][tid]["description"] = description
            else:
                name, tid = p
                self.s["tags"][tid]["name"] = name
            return
        if q.startswith("UPDATE hiroba_tag SET description"):
            description, tid = p
            self.s["tags"][tid]["description"] = description
            return
        if q.startswith("UPDATE hiroba_tag SET parent_tag_id"):
            # 移動時は display_order も同時更新する（ADR-0074、新しい兄弟集合の末尾へ再採番）。
            parent, new_order, tid = p
            self.s["tags"][tid]["parent"] = parent
            self.s["tags"][tid]["order"] = new_order
            return
        if q.startswith("UPDATE hiroba_tag SET display_order"):
            new_order, tid = p
            self.s["tags"][tid]["order"] = new_order
            return
        if q.startswith("UPDATE hiroba_tag SET folder_id"):
            folder, tid = p
            self.s["tags"][tid]["folder"] = folder
            return
        if q.startswith("DELETE FROM hiroba_tag_alias"):
            tid = p[0]
            # WHERE tag_id = %s（cascade）か WHERE id = %s（単体削除）かを区別
            if "WHERE tag_id" in q:
                for aid in [
                    aid for aid, a in self.s["aliases"].items() if a["tag_id"] == tid
                ]:
                    self.s["aliases"].pop(aid, None)
            else:
                self.s["aliases"].pop(tid, None)
            return
        if q.startswith("DELETE FROM hiroba_tag"):
            self.s["tags"].pop(p[0], None)
            return

        # --- display_order 採番・並べ替え（ADR-0074）。汎用SELECTに横取りされる前に判定する。 --- #
        # フォルダ（hiroba_tag_folder）はタグ（hiroba_tag）のプレフィックスに一致するため先に判定する。
        if "SELECT MAX(display_order) FROM hiroba_tag_folder" in q:
            if "IS NULL" in q:
                vals = [
                    f["order"]
                    for f in self.s["folders"].values()
                    if f.get("parent") is None and f.get("order") is not None
                ]
            else:
                vals = [
                    f["order"]
                    for f in self.s["folders"].values()
                    if f.get("parent") == p[0] and f.get("order") is not None
                ]
            self._result = [(max(vals) if vals else None,)]
            return
        if "SELECT MAX(display_order) FROM hiroba_tag" in q:
            if "IS NULL" in q:
                vals = [
                    t["order"]
                    for t in self.s["tags"].values()
                    if t.get("parent") is None and t.get("order") is not None
                ]
            else:
                vals = [
                    t["order"]
                    for t in self.s["tags"].values()
                    if t.get("parent") == p[0] and t.get("order") is not None
                ]
            self._result = [(max(vals) if vals else None,)]
            return
        if "SELECT id, display_order FROM hiroba_tag_folder" in q:
            if "IS NULL" in q:
                items = [
                    (fid, f["order"])
                    for fid, f in self.s["folders"].items()
                    if f.get("parent") is None
                ]
            else:
                items = [
                    (fid, f["order"])
                    for fid, f in self.s["folders"].items()
                    if f.get("parent") == p[0]
                ]
            self._result = sorted(items, key=lambda x: (x[1], x[0]))
            return
        if "SELECT id, display_order FROM hiroba_tag" in q:
            if "IS NULL" in q:
                items = [
                    (tid, t["order"])
                    for tid, t in self.s["tags"].items()
                    if t.get("parent") is None
                ]
            else:
                items = [
                    (tid, t["order"])
                    for tid, t in self.s["tags"].items()
                    if t.get("parent") == p[0]
                ]
            self._result = sorted(items, key=lambda x: (x[1], x[0]))
            return
        if "SELECT parent_folder_id FROM hiroba_tag_folder WHERE id = %s" in q:
            f = self.s["folders"].get(p[0])
            self._result = [(f["parent"],)] if f else []
            return

        # --- 参照系 --- #
        if "FROM ancestors WHERE id = %s" in q:
            # 循環参照検証の再帰CTE。タグ版（parent_tag_id）とフォルダ版（parent_folder_id）で
            # 参照するストアを切り替える（ADR-0073 でフォルダ版を追加）。
            store = self.s["folders"] if "parent_folder_id" in q else self.s["tags"]
            new_parent, target_id = p
            anc = set()
            cur = new_parent
            while cur is not None and cur not in anc:
                anc.add(cur)
                cur = store.get(cur, {}).get("parent")
            self._result = [(1,)] if target_id in anc else []
        # --- タグフォルダ（hiroba_tag のプレフィックスと衝突するため先に判定） --- #
        elif "FROM hiroba_tag WHERE folder_id = %s" in q:
            self._result = [
                (1,) for t in self.s["tags"].values() if t.get("folder") == p[0]
            ][:1]
        elif "FROM hiroba_tag_folder WHERE name = %s AND id <> %s" in q:
            self._result = [
                (1,)
                for fid, f in self.s["folders"].items()
                if f["name"] == p[0] and fid != p[1]
            ][:1]
        elif "FROM hiroba_tag_folder WHERE name = %s" in q:
            self._result = [
                (1,) for f in self.s["folders"].values() if f["name"] == p[0]
            ][:1]
        elif "SELECT 1 FROM hiroba_tag_folder WHERE id = %s" in q:
            self._result = [(1,)] if p[0] in self.s["folders"] else []
        elif "FROM hiroba_tag_folder ORDER BY display_order, id" in q:
            # 実DBと同じく (display_order, id) 昇順で返す（ADR-0074）。order 未設定は先頭扱い。
            self._result = [
                (fid, f["name"], f["description"], f.get("parent"), f.get("order"))
                for fid, f in sorted(
                    self.s["folders"].items(),
                    key=lambda kv: (
                        kv[1].get("order") if kv[1].get("order") is not None else float("-inf"),
                        kv[0],
                    ),
                )
            ]
        elif "FROM hiroba_tag_folder WHERE id = %s" in q:
            if p[0] in self.s["folders"]:
                f = self.s["folders"][p[0]]
                self._result = [
                    (p[0], f["name"], f["description"], f.get("parent"), f.get("order"))
                ]
        elif "FROM hiroba_qa_tag WHERE tag_id = %s" in q:
            self._result = [(1,)] if p[0] in self.s["qa_tag"] else []
        elif "FROM hiroba_tag WHERE parent_tag_id = %s" in q:
            self._result = [
                (1,) for t in self.s["tags"].values() if t["parent"] == p[0]
            ][:1]
        elif "FROM hiroba_tag_alias WHERE alias = %s" in q:
            self._result = [
                (1,) for a in self.s["aliases"].values() if a["alias"] == p[0]
            ][:1]
        elif "FROM hiroba_tag_alias WHERE id = %s" in q:
            self._result = [(1,)] if p[0] in self.s["aliases"] else []
        elif "SELECT id, alias FROM hiroba_tag_alias WHERE tag_id = %s" in q:
            self._result = [
                (aid, a["alias"])
                for aid, a in sorted(self.s["aliases"].items())
                if a["tag_id"] == p[0]
            ]
        elif "SELECT id, tag_id, alias FROM hiroba_tag_alias" in q:
            self._result = [
                (aid, a["tag_id"], a["alias"])
                for aid, a in sorted(self.s["aliases"].items())
            ]
        elif "WHERE name = %s AND id <> %s" in q:
            self._result = [
                (1,)
                for tid, t in self.s["tags"].items()
                if t["name"] == p[0] and tid != p[1]
            ][:1]
        elif "FROM hiroba_tag WHERE name = %s" in q:
            self._result = [
                (1,) for t in self.s["tags"].values() if t["name"] == p[0]
            ][:1]
        elif "SELECT 1 FROM hiroba_tag WHERE id = %s" in q:
            self._result = [(1,)] if p[0] in self.s["tags"] else []
        elif "FROM hiroba_tag ORDER BY display_order, id" in q:
            # 実DBと同じく (display_order, id) 昇順で返す（ADR-0074）。order 未設定は先頭扱い。
            self._result = [
                (
                    tid,
                    t["name"],
                    t["parent"],
                    t["description"],
                    t.get("folder"),
                    t.get("order"),
                )
                for tid, t in sorted(
                    self.s["tags"].items(),
                    key=lambda kv: (
                        kv[1].get("order") if kv[1].get("order") is not None else float("-inf"),
                        kv[0],
                    ),
                )
            ]
        elif "FROM hiroba_tag WHERE id = %s" in q:
            if p[0] in self.s["tags"]:
                t = self.s["tags"][p[0]]
                self._result = [
                    (
                        p[0],
                        t["name"],
                        t["parent"],
                        t["description"],
                        t.get("folder"),
                        t.get("order"),
                    )
                ]

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


class FakeTagDatabase:
    def __init__(self):
        self.store = {
            "tags": {},       # {id: {"name", "parent", "description", "folder"}}
            "aliases": {},    # {id: {"tag_id", "alias"}}
            "folders": {},    # {id: {"name", "description", "parent"}}  parent=parent_folder_id
            "qa_tag": set(),  # 参照されている tag_id の集合
            "next_tag_id": 1,
            "next_alias_id": 1,
            "next_folder_id": 1,
        }

    @contextmanager
    def cursor(self):
        yield FakeCursor(self.store)


@pytest.fixture
def repo():
    return TagRepository(FakeTagDatabase())


# --------------------------------------------------------------------------- #
# create_tag
# --------------------------------------------------------------------------- #
def test_create_root_and_child(repo):
    root = repo.create_tag("積算システム")
    child = repo.create_tag("操作方法", parent_tag_id=root.id)
    assert root.parent_tag_id is None
    assert child.parent_tag_id == root.id


def test_create_with_description(repo):
    node = repo.create_tag("積算システム", description="積算に関する情報")
    assert node.description == "積算に関する情報"


def test_create_duplicate_name_rejected(repo):
    repo.create_tag("認証")
    with pytest.raises(TagError):
        repo.create_tag("認証")


def test_create_under_missing_parent_rejected(repo):
    with pytest.raises(TagError):
        repo.create_tag("x", parent_tag_id=999)


# --------------------------------------------------------------------------- #
# description / alias（IMPL-202608060837）
# --------------------------------------------------------------------------- #
def test_set_tag_description(repo):
    a = repo.create_tag("A")
    node = repo.set_tag_description(a.id, "説明")
    assert node.description == "説明"
    node = repo.set_tag_description(a.id, None)
    assert node.description is None


def test_add_and_list_alias(repo):
    a = repo.create_tag("積算")
    added = repo.add_tag_alias(a.id, "見積")
    assert added["alias"] == "見積"
    assert added["tag_id"] == a.id
    node = repo.list_tags()[0]
    assert [al["alias"] for al in node.aliases] == ["見積"]


def test_add_duplicate_alias_rejected(repo):
    a = repo.create_tag("A")
    b = repo.create_tag("B")
    repo.add_tag_alias(a.id, "同義")
    with pytest.raises(TagError):
        repo.add_tag_alias(b.id, "同義")


def test_remove_alias(repo):
    a = repo.create_tag("A")
    added = repo.add_tag_alias(a.id, "x")
    repo.remove_tag_alias(added["id"])
    assert repo.list_tags()[0].aliases == []


# --------------------------------------------------------------------------- #
# move_tag / 循環参照
# --------------------------------------------------------------------------- #
def test_move_tag_under_self_rejected(repo):
    a = repo.create_tag("A")
    with pytest.raises(TagError):
        repo.move_tag(a.id, a.id)


def test_move_tag_under_descendant_rejected(repo):
    a = repo.create_tag("A")
    b = repo.create_tag("B", parent_tag_id=a.id)
    c = repo.create_tag("C", parent_tag_id=b.id)
    # A を、その子孫である C の下へ移そうとすると循環
    with pytest.raises(TagError):
        repo.move_tag(a.id, c.id)


def test_move_tag_valid(repo):
    a = repo.create_tag("A")
    b = repo.create_tag("B")
    moved = repo.move_tag(b.id, a.id)
    assert moved.parent_tag_id == a.id


# --------------------------------------------------------------------------- #
# delete_tag
# --------------------------------------------------------------------------- #
def test_delete_tag_with_children_rejected(repo):
    a = repo.create_tag("A")
    repo.create_tag("B", parent_tag_id=a.id)
    with pytest.raises(TagError):
        repo.delete_tag(a.id)


def test_delete_tag_referenced_by_qa_rejected(repo):
    a = repo.create_tag("A")
    repo.db.store["qa_tag"].add(a.id)
    with pytest.raises(TagError):
        repo.delete_tag(a.id)


def test_delete_unreferenced_tag_ok(repo):
    a = repo.create_tag("A")
    repo.delete_tag(a.id)
    assert repo.list_tags() == []


def test_delete_tag_cascades_aliases(repo):
    """削除可能なタグは紐づく tag_alias も連動して削除される（IMPL-202608060837 0節）。"""
    a = repo.create_tag("A")
    repo.add_tag_alias(a.id, "x")
    repo.add_tag_alias(a.id, "y")
    repo.delete_tag(a.id)
    assert repo.db.store["aliases"] == {}


# --------------------------------------------------------------------------- #
# list_tags 木構造
# --------------------------------------------------------------------------- #
def test_list_tags_builds_tree(repo):
    root = repo.create_tag("積算システム")
    child = repo.create_tag("操作方法", parent_tag_id=root.id)
    grand = repo.create_tag("空行挿入", parent_tag_id=child.id)

    tree = repo.list_tags()
    assert len(tree) == 1
    assert tree[0].id == root.id
    assert tree[0].children[0].id == child.id
    assert tree[0].children[0].children[0].id == grand.id


def test_list_tags_reflects_direct_db_change(repo):
    """tag テーブルを直接変更した直後に最新内容が返る（キャッシュしない設計・ADR-0006）。"""
    a = repo.create_tag("A")
    # DBを直接書き換え（Fake DBの内部ストアを直接操作）
    repo.db.store["tags"][a.id] = {"name": "A-renamed", "parent": None, "description": None}
    tree = repo.list_tags()
    assert tree[0].name == "A-renamed"


# --------------------------------------------------------------------------- #
# export_tags（IMPL-202608281500 / ADR-0065）
# --------------------------------------------------------------------------- #
def test_export_tags_flattens_tree_in_hierarchy_order(repo):
    """ツリーを親→子の階層順でフラット化し、parent_name を持ち回る。"""
    root = repo.create_tag("サポート", description="最上位")
    child = repo.create_tag("ログイン", parent_tag_id=root.id)
    grand = repo.create_tag("パスワード再設定", parent_tag_id=child.id)

    items = repo.export_tags()

    # 親が子より先に出現する階層順
    assert [i["name"] for i in items] == [
        "サポート",
        "ログイン",
        "パスワード再設定",
    ]
    by_name = {i["name"]: i for i in items}
    # ルート直下は parent_name=None、以下は親の name を持つ
    assert by_name["サポート"]["parent_name"] is None
    assert by_name["ログイン"]["parent_name"] == "サポート"
    assert by_name["パスワード再設定"]["parent_name"] == "ログイン"
    assert by_name["サポート"]["description"] == "最上位"
    # CSV は id を出力しないが、ツールの戻り値には含む（web_backend が参照しない）
    assert set(items[0].keys()) == {"id", "name", "parent_name", "description"}


def test_export_tags_excludes_aliases(repo):
    """エイリアスはエクスポート対象に含めない（ADR-0065 決定3）。"""
    a = repo.create_tag("認証")
    repo.add_tag_alias(a.id, "ログイン認証")

    items = repo.export_tags()

    assert len(items) == 1
    assert "aliases" not in items[0]
    assert "children" not in items[0]


# --------------------------------------------------------------------------- #
# タグフォルダ（ADR-0072 で新設、ADR-0073 で階層化）
# --------------------------------------------------------------------------- #
def test_create_and_list_tag_folder(repo):
    f = repo.create_tag_folder("対象システム", description="システム種別")
    assert f["name"] == "対象システム"
    assert f["description"] == "システム種別"
    assert f["parent_folder_id"] is None
    assert f["children"] == []
    folders = repo.list_tag_folders()
    assert [x["name"] for x in folders] == ["対象システム"]
    assert folders[0]["parent_folder_id"] is None
    assert folders[0]["children"] == []


def test_create_duplicate_folder_allowed(repo):
    # ADR-0073 決定1: name の一意性制約を撤廃。同名フォルダの作成は常に成功する。
    a = repo.create_tag_folder("文脈")
    b = repo.create_tag_folder("文脈")
    assert a["id"] != b["id"]
    assert [x["name"] for x in repo.list_tag_folders()] == ["文脈", "文脈"]


def test_rename_tag_folder(repo):
    f = repo.create_tag_folder("旧名")
    renamed = repo.rename_tag_folder(f["id"], "新名", description="説明")
    assert renamed["name"] == "新名"
    assert renamed["description"] == "説明"


def test_rename_folder_to_existing_name_allowed(repo):
    # ADR-0073 決定1: 同名フォルダへの改名も常に成功する。
    a = repo.create_tag_folder("A")
    b = repo.create_tag_folder("B")
    renamed = repo.rename_tag_folder(b["id"], "A")
    assert renamed["name"] == "A"
    assert {x["id"]: x["name"] for x in repo.list_tag_folders()} == {
        a["id"]: "A",
        b["id"]: "A",
    }


# --- フォルダ階層（ADR-0073） --- #
def test_create_folder_with_parent(repo):
    parent = repo.create_tag_folder("対象システム")
    child = repo.create_tag_folder("フロントエンド", parent_folder_id=parent["id"])
    assert child["parent_folder_id"] == parent["id"]


def test_create_folder_with_missing_parent_rejected(repo):
    with pytest.raises(TagError):
        repo.create_tag_folder("x", parent_folder_id=999)


def test_list_tag_folders_returns_tree(repo):
    root = repo.create_tag_folder("対象システム")
    front = repo.create_tag_folder("フロントエンド", parent_folder_id=root["id"])
    repo.create_tag_folder("バックエンド", parent_folder_id=root["id"])
    other = repo.create_tag_folder("文脈")  # 別ルート

    tree = repo.list_tag_folders()
    by_name = {n["name"]: n for n in tree}
    # ルートは「対象システム」「文脈」の2件
    assert set(by_name) == {"対象システム", "文脈"}
    child_names = {c["name"] for c in by_name["対象システム"]["children"]}
    assert child_names == {"フロントエンド", "バックエンド"}
    assert by_name["文脈"]["children"] == []
    # 深さ2の孫もネストされる
    web = repo.create_tag_folder("Web", parent_folder_id=front["id"])
    tree2 = repo.list_tag_folders()
    root2 = {n["name"]: n for n in tree2}["対象システム"]
    front2 = {c["name"]: c for c in root2["children"]}["フロントエンド"]
    assert [g["id"] for g in front2["children"]] == [web["id"]]
    assert other["parent_folder_id"] is None


def test_move_tag_folder(repo):
    a = repo.create_tag_folder("A")
    b = repo.create_tag_folder("B")
    moved = repo.move_tag_folder(b["id"], a["id"])
    assert moved["parent_folder_id"] == a["id"]
    # ルートへ戻す
    back = repo.move_tag_folder(b["id"], None)
    assert back["parent_folder_id"] is None


def test_move_tag_folder_to_self_rejected(repo):
    a = repo.create_tag_folder("A")
    with pytest.raises(TagError):
        repo.move_tag_folder(a["id"], a["id"])


def test_move_tag_folder_to_descendant_rejected(repo):
    a = repo.create_tag_folder("A")
    b = repo.create_tag_folder("B", parent_folder_id=a["id"])
    c = repo.create_tag_folder("C", parent_folder_id=b["id"])
    # A を自身の子孫 C の下へ移すと循環になるため拒否
    with pytest.raises(TagError):
        repo.move_tag_folder(a["id"], c["id"])


def test_move_tag_folder_missing_parent_rejected(repo):
    a = repo.create_tag_folder("A")
    with pytest.raises(TagError):
        repo.move_tag_folder(a["id"], 999)


def test_create_tag_with_folder(repo):
    f = repo.create_tag_folder("動作環境")
    node = repo.create_tag("Windows", folder_id=f["id"])
    assert node.folder_id == f["id"]


def test_create_tag_with_missing_folder_rejected(repo):
    with pytest.raises(TagError):
        repo.create_tag("x", folder_id=999)


def test_set_tag_folder_assign_and_clear(repo):
    f = repo.create_tag_folder("分類")
    a = repo.create_tag("A")
    assigned = repo.set_tag_folder(a.id, f["id"])
    assert assigned.folder_id == f["id"]
    cleared = repo.set_tag_folder(a.id, None)
    assert cleared.folder_id is None


def test_set_tag_folder_missing_folder_rejected(repo):
    a = repo.create_tag("A")
    with pytest.raises(TagError):
        repo.set_tag_folder(a.id, 999)


def test_delete_folder_referenced_by_tag_rejected(repo):
    f = repo.create_tag_folder("分類")
    repo.create_tag("A", folder_id=f["id"])
    with pytest.raises(TagError):
        repo.delete_tag_folder(f["id"])


def test_delete_unreferenced_folder_ok(repo):
    f = repo.create_tag_folder("分類")
    repo.delete_tag_folder(f["id"])
    assert repo.list_tag_folders() == []


def test_delete_folder_promotes_children_to_grandparent(repo):
    # ADR-0073 決定3: 子フォルダを持つフォルダを削除すると、子は削除対象の親へ繰り上がる。
    grand = repo.create_tag_folder("対象システム")
    parent = repo.create_tag_folder("Web系", parent_folder_id=grand["id"])
    child = repo.create_tag_folder("フロント", parent_folder_id=parent["id"])
    # タグは子フォルダに割り当てておき、folder_id が変化しないことを確認する
    tag = repo.create_tag("React", folder_id=child["id"])

    repo.delete_tag_folder(parent["id"])

    folders = {f["id"]: f for f in _flatten_folders(repo.list_tag_folders())}
    assert parent["id"] not in folders
    # child は削除対象 parent の親（grand）へ繰り上がる
    assert folders[child["id"]]["parent_folder_id"] == grand["id"]
    # 子フォルダに割り当てられたタグの folder_id は変化しない
    tree = repo.list_tags()
    assert {n.name: n.folder_id for n in _flatten_tags(tree)}["React"] == child["id"]
    assert tag.folder_id == child["id"]


def test_delete_root_folder_promotes_children_to_root(repo):
    # 削除対象がルートだった場合、子は新たにルートとなる（parent_folder_id=NULL）。
    root = repo.create_tag_folder("対象システム")
    child = repo.create_tag_folder("フロント", parent_folder_id=root["id"])
    repo.delete_tag_folder(root["id"])
    folders = repo.list_tag_folders()
    by_id = {f["id"]: f for f in folders}
    assert child["id"] in by_id
    assert by_id[child["id"]]["parent_folder_id"] is None


def _flatten_folders(tree):
    """フォルダツリーを平坦化する（テスト補助）。"""
    out = []

    def walk(nodes):
        for n in nodes:
            out.append(n)
            walk(n["children"])

    walk(tree)
    return out


def _flatten_tags(tree):
    """タグツリーを平坦化する（テスト補助）。"""
    out = []

    def walk(nodes):
        for n in nodes:
            out.append(n)
            walk(n.children)

    walk(tree)
    return out


def test_list_tags_includes_folder_id(repo):
    f = repo.create_tag_folder("分類")
    a = repo.create_tag("A", folder_id=f["id"])
    b = repo.create_tag("B")
    tree = repo.list_tags()
    by_name = {n.name: n for n in tree}
    assert by_name["A"].folder_id == f["id"]
    assert by_name["B"].folder_id is None
    # to_dict にも folder_id が含まれる
    assert by_name["A"].to_dict()["folder_id"] == f["id"]


# --------------------------------------------------------------------------- #
# display_order（表示順序・並べ替え, ADR-0074）
# --------------------------------------------------------------------------- #
def test_create_tag_appends_display_order_at_tail(repo):
    """新規タグは兄弟集合の末尾に GAP(1000.0) 刻みで採番される（ADR-0074 決定3）。"""
    a = repo.create_tag("A")
    b = repo.create_tag("B")
    c = repo.create_tag("C")
    assert a.display_order == 1000.0
    assert b.display_order == 2000.0
    assert c.display_order == 3000.0
    # to_dict にも display_order が含まれる
    assert a.to_dict()["display_order"] == 1000.0
    # 一覧は作成順（= display_order 昇順）で返る
    assert [n.name for n in repo.list_tags()] == ["A", "B", "C"]


def test_create_child_tag_display_order_is_per_sibling_set(repo):
    """子タグの display_order は親ごとの兄弟集合単位で採番される。"""
    root = repo.create_tag("root")
    c1 = repo.create_tag("c1", parent_tag_id=root.id)
    c2 = repo.create_tag("c2", parent_tag_id=root.id)
    # 子は親の集合とは独立に GAP から採番される
    assert c1.display_order == 1000.0
    assert c2.display_order == 2000.0


def test_reorder_tag_up_swaps_with_previous(repo):
    repo.create_tag("A")
    repo.create_tag("B")
    c = repo.create_tag("C")
    repo.reorder_tag(c.id, "up")
    assert [n.name for n in repo.list_tags()] == ["A", "C", "B"]


def test_reorder_tag_down_swaps_with_next(repo):
    a = repo.create_tag("A")
    repo.create_tag("B")
    repo.create_tag("C")
    repo.reorder_tag(a.id, "down")
    assert [n.name for n in repo.list_tags()] == ["B", "A", "C"]


def test_reorder_tag_up_at_head_is_noop(repo):
    a = repo.create_tag("A")
    b = repo.create_tag("B")
    before = a.display_order
    node = repo.reorder_tag(a.id, "up")
    assert node.display_order == before  # 変化しない
    assert [n.name for n in repo.list_tags()] == ["A", "B"]
    assert b.display_order == 2000.0


def test_reorder_tag_down_at_tail_is_noop(repo):
    repo.create_tag("A")
    b = repo.create_tag("B")
    before = b.display_order
    node = repo.reorder_tag(b.id, "down")
    assert node.display_order == before
    assert [n.name for n in repo.list_tags()] == ["A", "B"]


def test_reorder_tag_invalid_direction_rejected(repo):
    a = repo.create_tag("A")
    with pytest.raises(TagError):
        repo.reorder_tag(a.id, "sideways")


def test_reorder_missing_tag_rejected(repo):
    with pytest.raises(TagError):
        repo.reorder_tag(999, "up")


def test_move_tag_appends_to_new_sibling_tail(repo):
    """reparent 後は新しい親の兄弟集合の末尾へ display_order が再設定される（ADR-0074 決定3）。"""
    parent = repo.create_tag("parent")
    repo.create_tag("existing", parent_tag_id=parent.id)  # 末尾 = 1000.0
    orphan = repo.create_tag("orphan")  # ルート、order=2000.0
    moved = repo.move_tag(orphan.id, parent.id)
    # 新しい兄弟集合（existing=1000）の末尾 → 2000.0
    assert moved.display_order == 2000.0
    parent_node = repo.list_tags()[0]
    assert [c.name for c in parent_node.children] == ["existing", "orphan"]


def test_create_folder_appends_display_order_at_tail(repo):
    a = repo.create_tag_folder("A")
    b = repo.create_tag_folder("B")
    assert a["display_order"] == 1000.0
    assert b["display_order"] == 2000.0
    assert [f["name"] for f in repo.list_tag_folders()] == ["A", "B"]


def test_reorder_tag_folder_up_swaps_with_previous(repo):
    repo.create_tag_folder("A")
    repo.create_tag_folder("B")
    c = repo.create_tag_folder("C")
    repo.reorder_tag_folder(c["id"], "up")
    assert [f["name"] for f in repo.list_tag_folders()] == ["A", "C", "B"]


def test_reorder_tag_folder_boundary_noop_and_invalid(repo):
    a = repo.create_tag_folder("A")
    repo.create_tag_folder("B")
    # 先頭で up は No-Op
    repo.reorder_tag_folder(a["id"], "up")
    assert [f["name"] for f in repo.list_tag_folders()] == ["A", "B"]
    with pytest.raises(TagError):
        repo.reorder_tag_folder(a["id"], "diagonal")


def test_move_tag_folder_appends_to_new_sibling_tail(repo):
    parent = repo.create_tag_folder("parent")
    repo.create_tag_folder("existing", parent_folder_id=parent["id"])  # 1000.0
    orphan = repo.create_tag_folder("orphan")  # ルート
    moved = repo.move_tag_folder(orphan["id"], parent["id"])
    assert moved["display_order"] == 2000.0


# --------------------------------------------------------------------------- #
# search_knowledge（FastMCP が利用可能な場合のみ）
# --------------------------------------------------------------------------- #
def test_search_knowledge_min_score_filter():
    pytest.importorskip("mcp")
    from mcp.server.fastmcp import FastMCP

    from knowledge_mcp.models.document import Document
    from knowledge_mcp.mcp.tools import register_tools

    class FakeService:
        def search(self, query, tags=None, category=None, top_k=5):
            return [
                Document("a", "qa", "A", "", 0.9, {}),
                Document("b", "qa", "B", "", 0.1, {}),
            ]

    mcp = FastMCP(name="test")
    register_tools(
        mcp,
        FakeService(),
        tag_repository=None,
        qa_management_repository=None,
        default_top_k=5,
    )

    tool = mcp._tool_manager.get_tool("search_knowledge")
    out = tool.fn(query="q", min_score=0.5)
    ids = [r["id"] for r in out["results"]]
    assert ids == ["a"]
