"""エントリポイント（実装指示書 T9）。

Knowledge MCP サーバを Streamable HTTP で起動する。
MCPエンドポイントは既定で /mcp、ヘルスチェックは /health に公開される。

    python -m knowledge_mcp.main
"""

from __future__ import annotations

from .mcp.server import create_server


def main() -> None:
    mcp = create_server()
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
