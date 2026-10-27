# knowledge_mcp/src/knowledge_mcp/mcp — MCP サーバとツール定義

FastMCP（`mcp` パッケージ 1.x）を使った MCP サーバの組み立てと、公開する MCP ツールの定義です。トランスポートは Streamable HTTP（ADR-0002）。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`server.py`](server.py) | `create_server()`。環境変数（`DATABASE_URL`・`EMBEDDING_PROVIDER`・`KNOWLEDGE_MCP_PORT`・`TAG_SIMILARITY_WEIGHT` 等）から DB 接続・埋め込み関数（LM Studio または Bedrock、タイムアウト設定は ADR-0102）・各リポジトリ・`SearchService` を組み立て、ツールを登録し `/health` を追加した FastMCP を返す。`main.py` から呼ばれる。 |
| [`tools.py`](tools.py) | `register_tools()`。`search_knowledge` と、タグ・タグフォルダ・QA・言い換え質問文・トラブルシューティング記事の管理ツールを FastMCP に登録する薄いラッパ。業務エラー（`TagError`・`QaError` 等）は `ToolError` に変換して返す。 |
| [`schemas.py`](schemas.py) | 主なツール（`search_knowledge`・タグ・タグフォルダ・QA・言い換え質問文）の入出力 JSON Schema を定数で持つ仕様の控え。FastMCP は関数シグネチャからスキーマを自動生成するため、コードからは参照されていない。 |
