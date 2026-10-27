# knowledge_mcp/src/knowledge_mcp — Knowledge MCP サーバのパッケージ

Knowledge MCP サーバ本体です。`mcp/` が FastMCP サーバの組み立てとツール定義、`repository/` が DB への SQL、`services/` が複数ソースの検索結果の統合、`models/` がデータ型、`db/` が DB 接続を担います（IMPL-202608041013 / ADR-0001〜0006）。

## 構成

| 名前 | 説明 |
|---|---|
| [`db/`](db/README.md) | PostgreSQL への接続ファクトリ（操作ごとに接続を開閉）と pgvector 用のベクトル文字列変換。 |
| [`mcp/`](mcp/README.md) | 環境変数から依存を組み立てる FastMCP サーバ生成、MCP ツールの登録、ツール入出力の JSON Schema 定数。 |
| [`models/`](models/README.md) | 検索結果・QA・タグ・言い換え質問文・トラブルシューティング記事のデータクラスと業務エラー例外。 |
| [`repository/`](repository/README.md) | 検索用（ベクトル近傍＋タグ類似度）と管理用（CRUD・CSV 一括取込/出力）のリポジトリ、共通スコアリング。 |
| [`services/`](services/README.md) | 複数リポジトリの検索結果を score 降順で統合する `SearchService`。 |
| [`__init__.py`](__init__.py) | パッケージ宣言（docstring のみ）。 |
| [`main.py`](main.py) | エントリポイント。`mcp/server.py` の `create_server()` で作ったサーバを Streamable HTTP で起動する。`python -m knowledge_mcp.main`（Dockerfile の CMD）や `knowledge-mcp` コマンドから呼ばれる。 |
