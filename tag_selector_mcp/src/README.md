# tag_selector_mcp/src — Tag Selector MCP のソースルート

src レイアウトのソースルートです。`pyproject.toml` の `[tool.setuptools.packages.find] where = ["src"]` により、この直下のパッケージがインストール対象になります。

## 構成

| 名前 | 説明 |
|---|---|
| [`tag_selector_mcp/`](tag_selector_mcp/README.md) | Tag Selector MCP サーバ本体のパッケージ（エントリポイント、MCP ツール、タグ選択ロジック、LLM クライアント、DB 接続）。 |
