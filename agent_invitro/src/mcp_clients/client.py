"""MultiServerMCPClient のセットアップとツール取得（実装指示書 5.2 / T5 / ADR-0021）。"""

from __future__ import annotations

from langchain_mcp_adapters.client import MultiServerMCPClient


def build_mcp_client(
    tag_selector_mcp_url: str, knowledge_mcp_url: str
) -> MultiServerMCPClient:
    """Tag Selector MCP・Knowledge MCP の2サーバーへの接続設定を持つ client を構築する。

    Settings オブジェクトを直接受け取らず、必要な2つのURLをプリミティブな引数として
    直接受け取る（ADR-0033）。呼び出し元（main.py）が Settings からの値の展開を行う。
    転送方式はいずれも streamable_http を指定する
    （ADR-0021、既存2サーバーの実装と一致）。
    """
    return MultiServerMCPClient(
        {
            "tag_selector_mcp": {
                "url": tag_selector_mcp_url,
                "transport": "streamable_http",
            },
            "knowledge_mcp": {
                "url": knowledge_mcp_url,
                "transport": "streamable_http",
            },
        }
    )


async def load_tools(client: MultiServerMCPClient) -> list:
    """client.get_tools() を呼び出し、LangChain Tool のリストを返す。

    select_tags（tag_selector_mcp）・search_knowledge（knowledge_mcp）等を含む。
    非同期であるため、IPython の top-level await または asyncio 実行コンテキスト内で呼ぶこと。
    """
    return await client.get_tools()
