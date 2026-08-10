"""Knowledge MCP 用の MCP クライアントラッパー（実装指示書 IMPL-202608060837 4.4 / T9, T13）。

MCP Python SDK の Streamable HTTP クライアントを用いて Knowledge MCP のツールを呼び出す。
0節の決定に従い、**リクエストごとにセッションを新規に張り、処理完了後にクローズする**
（コネクションプール的な維持は行わない）。

Knowledge MCP 側の業務エラー（ToolError、= QaError/TagError 相当）は KnowledgeMcpError へ変換する。
接続失敗・タイムアウト等の基盤エラーはラップせずそのまま送出する（呼び出し元で 5xx になる）。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class KnowledgeMcpError(Exception):
    """Knowledge MCP 側の業務エラー（QaError/TagError 相当）をラップする例外。"""

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


class KnowledgeMcpClient:
    def __init__(self, url: str):
        self.url = url  # 環境変数 KNOWLEDGE_MCP_URL（例: http://knowledge_mcp:8100/mcp）

    async def call_tool(self, name: str, arguments: Optional[dict] = None) -> Any:
        """Knowledge MCP のツールを1回呼び出し、結果（辞書）を返す。

        業務エラー（isError=True）は KnowledgeMcpError へ変換する。
        呼び出し完了後はセッション・トランスポートを必ずクローズする（async with で保証）。
        """
        arguments = arguments or {}
        async with streamablehttp_client(self.url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)

        if getattr(result, "isError", False):
            raise KnowledgeMcpError(_first_text(result) or f"{name} failed")

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
