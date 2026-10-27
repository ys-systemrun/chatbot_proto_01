# knowledge_mcp/src/knowledge_mcp/services — サービス層

複数の検索リポジトリをまとめるサービス層です。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`search_service.py`](search_service.py) | `SearchService`。登録された各 `Repository`（現在は `QARepository` と `TroubleshootingRepository`、ADR-0078）の検索結果を集め、score 降順で `top_k` 件に切り詰めて返す。`search_knowledge` ツールから呼ばれる。 |
