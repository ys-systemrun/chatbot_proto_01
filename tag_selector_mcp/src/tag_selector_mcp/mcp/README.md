# tag_selector_mcp/src/tag_selector_mcp/mcp — MCP サーバとツール定義

FastMCP（`mcp` パッケージ 1.x）を使った MCP サーバの組み立てと、公開する MCP ツールの定義です。トランスポートは Streamable HTTP（ADR-0007）。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`server.py`](server.py) | `build_server()`。環境変数（`DATABASE_URL`・`LLM_PROVIDER`・`TAXONOMY_RELOAD_INTERVAL_SEC`・`TAG_SELECTOR_DEFAULT_MAX_TAGS` 等）から DB 接続・LLM クライアント・各エンジンを組み立て、ツールと `/health` を登録した FastMCP を、起動時ロードと定期リロードに必要な `TagMetadataRepository` とリロード間隔と一緒に返す。`main.py` から呼ばれる。FastMCP だけを返す `create_server()` もある。 |
| [`tools.py`](tools.py) | `register_tools()`。`select_tags`・`list_taxonomy`・`reload_taxonomy` を FastMCP に登録する。LLM 接続失敗や DB 参照失敗は `ToolError` に変換して返す。 |
| [`schemas.py`](schemas.py) | 3 ツールの入出力 JSON Schema を定数で持つ仕様の控え。FastMCP は関数シグネチャからスキーマを自動生成するため、コードからは参照されていない。 |
