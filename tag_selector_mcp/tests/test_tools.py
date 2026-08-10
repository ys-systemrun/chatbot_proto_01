"""MCPツール（select_tags / list_taxonomy / reload_taxonomy）の単体テスト（実装指示書 9.1）。

FastMCP が利用可能な場合のみ、ツールハンドラの入出力・エラー変換を検証する。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tag_selector_mcp.models.tag import SelectedTag, TagRecord


class FakeUseCase:
    def __init__(self, selected=None, error=None):
        self._selected = selected or []
        self._error = error
        self.calls = []

    def execute(self, query, max_tags=3, confidence_threshold=0.0):
        self.calls.append((query, max_tags, confidence_threshold))
        if self._error is not None:
            raise self._error
        return self._selected


class FakeRepo:
    def __init__(self, tags=None, reload_error=None):
        self._tags = tags or []
        self._reload_error = reload_error
        self.reload_called = 0

    def all_tags(self):
        return list(self._tags)

    def tag_count(self):
        return len(self._tags)

    def reload(self):
        self.reload_called += 1
        if self._reload_error is not None:
            raise self._reload_error


def _register(use_case, repo):
    from mcp.server.fastmcp import FastMCP

    from tag_selector_mcp.mcp.tools import register_tools

    mcp = FastMCP(name="test")
    register_tools(mcp, select_tags_use_case=use_case, tag_repository=repo)
    return mcp


def test_select_tags_returns_serialized():
    pytest.importorskip("mcp")
    use_case = FakeUseCase(
        selected=[SelectedTag(id=1, name="A", score=0.9, path=["A"])]
    )
    mcp = _register(use_case, FakeRepo())
    tool = mcp._tool_manager.get_tool("select_tags")
    out = tool.fn(query="積算", max_tags=2, confidence_threshold=0.1)
    assert out == {"selected": [{"id": 1, "name": "A", "score": 0.9, "path": ["A"]}]}
    assert use_case.calls == [("積算", 2, 0.1)]


def test_select_tags_error_becomes_tool_error():
    pytest.importorskip("mcp")
    from mcp.server.fastmcp.exceptions import ToolError

    use_case = FakeUseCase(error=RuntimeError("LLM down"))
    mcp = _register(use_case, FakeRepo())
    tool = mcp._tool_manager.get_tool("select_tags")
    with pytest.raises(ToolError):
        tool.fn(query="x")


def test_list_taxonomy_serializes_records():
    pytest.importorskip("mcp")
    repo = FakeRepo(
        tags=[
            TagRecord(id=3, name="積算システム", description="d", parent_tag_id=None, aliases=["積算"]),
        ]
    )
    mcp = _register(FakeUseCase(), repo)
    tool = mcp._tool_manager.get_tool("list_taxonomy")
    out = tool.fn()
    assert out == {
        "tags": [
            {
                "id": 3,
                "name": "積算システム",
                "description": "d",
                "parent_tag_id": None,
                "aliases": ["積算"],
            }
        ]
    }


def test_reload_taxonomy_returns_count():
    pytest.importorskip("mcp")
    repo = FakeRepo(tags=[TagRecord(id=1, name="A"), TagRecord(id=2, name="B")])
    mcp = _register(FakeUseCase(), repo)
    tool = mcp._tool_manager.get_tool("reload_taxonomy")
    out = tool.fn()
    assert out == {"reloaded": True, "tag_count": 2}
    assert repo.reload_called == 1


def test_reload_taxonomy_error_becomes_tool_error():
    pytest.importorskip("mcp")
    from mcp.server.fastmcp.exceptions import ToolError

    repo = FakeRepo(reload_error=RuntimeError("db down"))
    mcp = _register(FakeUseCase(), repo)
    tool = mcp._tool_manager.get_tool("reload_taxonomy")
    with pytest.raises(ToolError):
        tool.fn()
