# agent_invitro/src/mcp_clients — MCP クライアント

Tag Selector MCP（`select_tags`）と Knowledge MCP（`search_knowledge`）へ streamable_http で接続し、LangChain のツールとして取得します（ADR-0021）。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`client.py`](client.py) | `build_mcp_client(tag_selector_mcp_url, knowledge_mcp_url)` で 2 サーバー分の `MultiServerMCPClient` を作り、`load_tools(client)`（async）でツール一覧を取得する。IPython 経路と `main/api/dependencies.py` から使う。 |
