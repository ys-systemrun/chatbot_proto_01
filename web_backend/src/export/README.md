# web_backend/src/export/ — 全データエクスポートのダンプ生成

`GET /api/export` 用に、ナレッジ データベースと conversation データベースの全16テーブルを読み取り専用でダンプし、CSV または SQL 形式の ZIP を作るモジュール（ADR-0046 / ADR-0047）。pg_dump は使わず psycopg2 で組み立てる。呼び出し元は `main/controllers/export_controller.py`。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | モジュールの目的・責務分離方針を書いた docstring のみ。 |
| [`dump.py`](dump.py) | テーブルを CSV バイト列／SQL（CREATE TABLE + バッチ INSERT）文字列に変換する関数群と、`embedding` 列の VECTOR 次元を実 DB から検出する `detect_vector_dim`。 |
| [`tables.py`](tables.py) | エクスポート対象テーブルの定義（`TableSpec`: DB 種別・カラム・CSV 除外列・ORDER BY・DDL）と、外部キー順に並べた `KNOWLEDGE_TABLES` / `CONVERSATION_TABLES`。全消去インポート（ADR-0066）もこの集合を対象とする。 |
| [`zipper.py`](zipper.py) | ファイル名→中身の辞書をメモリ上で ZIP にまとめる `build_zip`（標準ライブラリのみ）。 |
