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
        if q.startswith("INSERT INTO tag_alias"):
            new_id = self.s["next_alias_id"]
            self.s["next_alias_id"] += 1
            self.s["aliases"][new_id] = {"tag_id": p[0], "alias": p[1]}
            self._result = [(new_id,)]
            return
        if q.startswith("INSERT INTO tag"):
            new_id = self.s["next_tag_id"]
            self.s["next_tag_id"] += 1
            self.s["tags"][new_id] = {
                "name": p[0],
                "parent": p[1],
                "description": p[2] if len(p) > 2 else None,
            }
            self._result = [(new_id,)]
            return
        if q.startswith("UPDATE tag SET name"):
            if "description" in q:
                name, description, tid = p
                self.s["tags"][tid]["name"] = name
                self.s["tags"][tid]["description"] = description
            else:
                name, tid = p
                self.s["tags"][tid]["name"] = name
            return
        if q.startswith("UPDATE tag SET description"):
            description, tid = p
            self.s["tags"][tid]["description"] = description
            return
        if q.startswith("UPDATE tag SET parent_tag_id"):
            parent, tid = p
            self.s["tags"][tid]["parent"] = parent
            return
        if q.startswith("DELETE FROM tag_alias"):
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
        if q.startswith("DELETE FROM tag"):
            self.s["tags"].pop(p[0], None)
            return

        # --- 参照系 --- #
        if "FROM ancestors WHERE id = %s" in q:
            new_parent, tag_id = p
            anc = set()
            cur = new_parent
            while cur is not None and cur not in anc:
                anc.add(cur)
                cur = self.s["tags"].get(cur, {}).get("parent")
            self._result = [(1,)] if tag_id in anc else []
        elif "FROM qa_tag WHERE tag_id = %s" in q:
            self._result = [(1,)] if p[0] in self.s["qa_tag"] else []
        elif "FROM tag WHERE parent_tag_id = %s" in q:
            self._result = [
                (1,) for t in self.s["tags"].values() if t["parent"] == p[0]
            ][:1]
        elif "FROM tag_alias WHERE alias = %s" in q:
            self._result = [
                (1,) for a in self.s["aliases"].values() if a["alias"] == p[0]
            ][:1]
        elif "FROM tag_alias WHERE id = %s" in q:
            self._result = [(1,)] if p[0] in self.s["aliases"] else []
        elif "SELECT id, alias FROM tag_alias WHERE tag_id = %s" in q:
            self._result = [
                (aid, a["alias"])
                for aid, a in sorted(self.s["aliases"].items())
                if a["tag_id"] == p[0]
            ]
        elif "SELECT id, tag_id, alias FROM tag_alias" in q:
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
        elif "FROM tag WHERE name = %s" in q:
            self._result = [
                (1,) for t in self.s["tags"].values() if t["name"] == p[0]
            ][:1]
        elif "SELECT 1 FROM tag WHERE id = %s" in q:
            self._result = [(1,)] if p[0] in self.s["tags"] else []
        elif "ORDER BY id" in q and "FROM tag" in q:
            self._result = [
                (tid, t["name"], t["parent"], t["description"])
                for tid, t in sorted(self.s["tags"].items())
            ]
        elif "FROM tag WHERE id = %s" in q:
            if p[0] in self.s["tags"]:
                t = self.s["tags"][p[0]]
                self._result = [(p[0], t["name"], t["parent"], t["description"])]

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


class FakeTagDatabase:
    def __init__(self):
        self.store = {
            "tags": {},       # {id: {"name", "parent", "description"}}
            "aliases": {},    # {id: {"tag_id", "alias"}}
            "qa_tag": set(),  # 参照されている tag_id の集合
            "next_tag_id": 1,
            "next_alias_id": 1,
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
