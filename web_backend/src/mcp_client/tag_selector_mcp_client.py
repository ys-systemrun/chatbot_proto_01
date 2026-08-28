"""Tag Selector MCP 用の MCP クライアントラッパー（IMPL-202608260909 T4、ADR-0049）。

既存の KnowledgeMcpClient（web_backend/src/mcp_client/knowledge_mcp_client.py）と全く同一の
方式（Streamable HTTP、リクエストごとに新規セッション、業務エラーの専用例外への変換）を、
呼び出し先を tag_selector_mcp に変えて複製する。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class TagSelectorMcpError(Exception):
    """Tag Selector MCP 側の業務エラーをラップする例外。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _first_text(result) -> str:
    """CallToolResult.content から最初のテキストブロックを取り出す。"""
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            return text
    return ""


class TagSelectorMcpClient:
    def __init__(self, url: str):
        self.url = url  # 環境変数 TAG_SELECTOR_MCP_URL（例: http://tag_selector_mcp:8200/mcp）

    async def call_tool(self, name: str, arguments: Optional[dict] = None) -> Any:
        """Tag Selector MCP のツールを1回呼び出し、結果（辞書）を返す。

        業務エラー（isError=True）は TagSelectorMcpError へ変換する。
        呼び出し完了後はセッション・トランスポートを必ずクローズする（async with で保証）。
        """
        arguments = arguments or {}
        async with streamablehttp_client(self.url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)

        if getattr(result, "isError", False):
            raise TagSelectorMcpError(_first_text(result) or f"{name} failed")

        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return structured

        text = _first_text(result)
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
