# knowledge_mcp/src — Knowledge MCP のソースルート

src レイアウトのソースルートです。`pyproject.toml` の `[tool.setuptools.packages.find] where = ["src"]` により、この直下のパッケージがインストール対象になります。

## 構成

| 名前 | 説明 |
|---|---|
| [`knowledge_mcp/`](knowledge_mcp/README.md) | Knowledge MCP サーバ本体のパッケージ（エントリポイント、MCP ツール、リポジトリ、モデル、DB 接続）。 |
