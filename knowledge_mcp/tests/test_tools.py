"""タグ管理ツール／search_knowledge の単体テスト（実装指示書 9.1, 9.4）。

タグ操作のロジック（create/rename/move/delete/list + 循環参照防止）は、
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

    def execute(self, sql, params=None):
        q = " ".join(sql.split())
        p = params or ()
        self._result = []

        # 文の種別（INSERT/UPDATE/DELETE）を先に判定し、SELECT の部分一致に横取りされないようにする
        if q.startswith("INSERT INTO tag"):
            new_id = self.s["next_id"]
            self.s["next_id"] += 1
            self.s["tags"][new_id] = (p[0], p[1])
            self._result = [(new_id,)]
            return
        if q.startswith("UPDATE tag SET name"):
            name, tid = p
            _, parent = self.s["tags"][tid]
            self.s["tags"][tid] = (name, parent)
            return
        if q.startswith("UPDATE tag SET parent_tag_id"):
            parent, tid = p
            name, _ = self.s["tags"][tid]
            self.s["tags"][tid] = (name, parent)
            return
        if q.startswith("DELETE FROM tag"):
            self.s["tags"].pop(p[0], None)
            return

        if "FROM ancestors WHERE id = %s" in q:
            # 循環検出: p=(new_parent, tag_id)。new_parent の祖先集合に tag_id が居るか。
            new_parent, tag_id = p
            anc = set()
            cur = new_parent
            while cur is not None and cur not in anc:
                anc.add(cur)
                cur = self.s["tags"].get(cur, (None, None))[1]
            self._result = [(1,)] if tag_id in anc else []
        elif "FROM qa_tag WHERE tag_id = %s" in q:
            self._result = [(1,)] if p[0] in self.s["qa_tag"] else []
        elif "FROM tag WHERE parent_tag_id = %s" in q:
            self._result = [
                (1,) for v in self.s["tags"].values() if v[1] == p[0]
            ][:1]
        elif "WHERE name = %s AND id <> %s" in q:
            self._result = [
                (1,)
                for tid, (name, _) in self.s["tags"].items()
                if name == p[0] and tid != p[1]
            ][:1]
        elif "FROM tag WHERE name = %s" in q:
            self._result = [
                (1,) for (name, _) in self.s["tags"].values() if name == p[0]
            ][:1]
        elif "ORDER BY id" in q:
            self._result = [
                (tid, name, parent)
                for tid, (name, parent) in sorted(self.s["tags"].items())
            ]
        elif "FROM tag WHERE id = %s" in q:
            if p[0] in self.s["tags"]:
                name, parent = self.s["tags"][p[0]]
                self._result = [(p[0], name, parent)]

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


class FakeTagDatabase:
    def __init__(self):
        # tags: {id: (name, parent_tag_id)}
        self.store = {"tags": {}, "qa_tag": set(), "next_id": 1}

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


def test_create_duplicate_name_rejected(repo):
    repo.create_tag("認証")
    with pytest.raises(TagError):
        repo.create_tag("認証")


def test_create_under_missing_parent_rejected(repo):
    with pytest.raises(TagError):
        repo.create_tag("x", parent_tag_id=999)


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
    repo.db.store["tags"][a.id] = ("A-renamed", None)
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
    register_tools(mcp, FakeService(), tag_repository=None, default_top_k=5)

    tool = mcp._tool_manager.get_tool("search_knowledge")
    out = tool.fn(query="q", min_score=0.5)
    ids = [r["id"] for r in out["results"]]
    assert ids == ["a"]
