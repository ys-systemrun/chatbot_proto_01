"""build_agent() のスモークテスト（実装指示書 9.2 / 任意）。

モックの LLM・tools を用い、実際の MCP サーバー・LM Studio への接続なしに
build_agent() がエージェントを構築できることを確認する。
"""

from __future__ import annotations

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from agent_invitro.graph.agent import SYSTEM_PROMPT, build_agent


@tool
def select_tags(query: str) -> list[str]:
    """質問文に関連するタグを返す（モック）。"""
    return ["dummy_tag"]


@tool
def search_knowledge(tags: list[str]) -> str:
    """タグに基づき社内QAを検索する（モック）。"""
    return "dummy result"


def test_build_agent_constructs_graph():
    llm = FakeMessagesListChatModel(responses=[AIMessage(content="ok")])
    tools = [select_tags, search_knowledge]

    agent = build_agent(llm, tools)

    assert agent is not None
    # コンパイル済みグラフは invoke を持つ
    assert hasattr(agent, "invoke")


def test_system_prompt_mentions_tool_order():
    assert "select_tags" in SYSTEM_PROMPT
    assert "search_knowledge" in SYSTEM_PROMPT
