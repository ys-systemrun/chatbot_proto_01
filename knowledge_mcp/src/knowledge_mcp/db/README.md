# knowledge_mcp/src/knowledge_mcp/db — DB 接続

ナレッジ DB への psycopg2 接続を提供します。常駐サーバでの接続失効を避け、タグ等をキャッシュしない方針（ADR-0006）と整合させるため、DB 操作ごとに接続を開いて閉じます。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`connection.py`](connection.py) | `Database`（`DATABASE_URL` から操作ごとに接続を作り、`cursor()` コンテキストで commit / rollback / close まで行うファクトリ）と、埋め込みベクトルを pgvector のリテラル文字列にする `to_vector_str()`。`mcp/server.py` で生成され各リポジトリへ DI される。psycopg2 は接続時に遅延 import する。 |
