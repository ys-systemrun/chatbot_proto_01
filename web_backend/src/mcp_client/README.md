# web_backend/src/mcp_client/ — MCP サーバー呼び出し用クライアント

MCP Python SDK の Streamable HTTP クライアントで Knowledge MCP・Tag Selector MCP のツールを呼ぶラッパー。リクエストごとにセッションを張って閉じ、MCP 側の業務エラーは専用例外に変換する（`KnowledgeMcpError` は `app.py` で 409 に変換される）。管理UI系・検証系の Controller から使われる。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | 2 つのクライアントと例外クラスを再エクスポートする。 |
| [`knowledge_mcp_client.py`](knowledge_mcp_client.py) | `KnowledgeMcpClient` / `KnowledgeMcpError`。接続先は `KNOWLEDGE_MCP_URL`。QA・タグ・言い換え・トラブルシューティング記事の管理ツールや search_knowledge の呼び出しに使う。 |
| [`tag_selector_mcp_client.py`](tag_selector_mcp_client.py) | `TagSelectorMcpClient` / `TagSelectorMcpError`。接続先は `TAG_SELECTOR_MCP_URL`。検証実行で select_tags を呼ぶために使う（ADR-0049）。方式は Knowledge MCP 用と同一。 |
