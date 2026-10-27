# tag_selector_mcp/src/tag_selector_mcp/db — DB 接続

ナレッジ DB への psycopg2 接続を提供します。Knowledge MCP の `db/connection.py` と同じ方針で、DB 操作ごとに接続を開いて閉じます。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`connection.py`](connection.py) | `Database`。`DATABASE_URL` から操作ごとに接続を作り、`cursor()` コンテキストで commit / rollback / close まで行うファクトリ。`mcp/server.py` で生成され、`TagMetadataRepository` がロード・リロード時の読み取りに使う。psycopg2 は接続時に遅延 import する。 |
