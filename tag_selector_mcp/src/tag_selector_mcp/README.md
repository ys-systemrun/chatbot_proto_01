# tag_selector_mcp/src/tag_selector_mcp — Tag Selector MCP サーバのパッケージ

Tag Selector MCP サーバ本体です。`mcp/` が FastMCP サーバの組み立てとツール定義、`application/` がタグ選択のユースケース、`infrastructure/` が LLM クライアントとタグのキャッシュ、`models/` がデータ型、`db/` が DB 接続を担います（IMPL-202608051712 / ADR-0007〜0012）。

## 構成

| 名前 | 説明 |
|---|---|
| [`application/`](application/README.md) | タグ選択の処理本体。同義語照合（RetrievalEngine）→ LLM 選択（InferenceEngine）を束ねるユースケース。 |
| [`db/`](db/README.md) | PostgreSQL への接続ファクトリ（操作ごとに接続を開閉）。 |
| [`infrastructure/`](infrastructure/README.md) | 外部とつなぐ実装。LLM クライアント（LM Studio / Bedrock）と、タグ知識ベースをメモリにキャッシュするリポジトリ。 |
| [`mcp/`](mcp/README.md) | 環境変数から依存を組み立てる FastMCP サーバ生成、MCP ツールの登録、ツール入出力の JSON Schema 定数。 |
| [`models/`](models/README.md) | タグ知識ベースの 1 件 `TagRecord` と選択結果 `SelectedTag`。 |
| [`__init__.py`](__init__.py) | パッケージ宣言（docstring のみ）。 |
| [`main.py`](main.py) | エントリポイント。`build_server()` でサーバを作り、タグ知識ベースを起動時ロードし、定期リロードのデーモンスレッドを開始してから Streamable HTTP で起動する（ADR-0011）。`python -m tag_selector_mcp.main`（Dockerfile の CMD）や `tag-selector-mcp` コマンドから呼ばれる。 |
