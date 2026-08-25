"""IPython 向けエントリポイント（実装指示書 5.5 / T8 / ADR-0019）。

使用例（IPython の top-level await を利用）:

    from agent_invitro.main.ipython.main import build, run
    agent, mcp_client = await build()
    await run(agent, "積算システムの操作方法を教えてください")
"""

from __future__ import annotations

from ...config import load_settings
from ...graph.agent import build_agent
from ...llm import build_llm
from ...mcp_clients.client import build_mcp_client, load_tools


async def build():
    """settings, mcp_client, tools, llm, agent を構築し、(agent, mcp_client) を返す。

    main.py は Settings の形状を知る唯一のモジュールとして、load_settings() で
    取得した値をフィールドごとに展開し、各モジュールの関数へキーワード引数として
    明示的に渡す（ADR-0033、コンポジションルート）。
    """
    settings = load_settings()

    mcp_client = build_mcp_client(
        tag_selector_mcp_url=settings.tag_selector_mcp_url,
        knowledge_mcp_url=settings.knowledge_mcp_url,
    )
    tools = await load_tools(mcp_client)

    llm = build_llm(
        llm_provider=settings.llm_provider,
        lmstudio_chat_url=settings.lmstudio_chat_url,
        lmstudio_chat_model=settings.lmstudio_chat_model,
        bedrock_chat_model_id=settings.bedrock_chat_model_id,
        bedrock_region=settings.bedrock_region,
    )
    agent = build_agent(llm, tools)
    return agent, mcp_client


async def run(agent, query: str) -> str:
    """agent.ainvoke で1クエリを実行し、途中のツール呼び出しと最終回答をログ出力する。

    実行中に呼ばれたツール名・引数・ツール応答、および最終回答を標準出力へ出力する
    （要件定義書 6.5節）。最終回答のテキストを返り値として返す。
    """
    result = await agent.ainvoke({"messages": [("user", query)]})
    messages = result["messages"]

    print("=" * 60)
    print(f"[query] {query}")
    print("-" * 60)

    for msg in messages:
        # ツール呼び出し（AIMessage.tool_calls）
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for call in tool_calls:
                name = call.get("name")
                args = call.get("args")
                print(f"[tool_call] {name} args={args}")

        # ツール応答（ToolMessage）
        if msg.__class__.__name__ == "ToolMessage":
            tool_name = getattr(msg, "name", "?")
            print(f"[tool_result] {tool_name} -> {msg.content}")

    final = messages[-1]
    answer = final.content if hasattr(final, "content") else str(final)
    print("-" * 60)
    print(f"[answer] {answer}")
    print("=" * 60)

    return answer
