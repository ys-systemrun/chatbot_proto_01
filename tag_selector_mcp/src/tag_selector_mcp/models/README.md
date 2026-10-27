# tag_selector_mcp/src/tag_selector_mcp/models — データモデル

タグ知識ベースと選択結果のデータクラスです。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`tag.py`](tag.py) | `TagRecord`（`tag` と `tag_alias` をまとめたタグ知識ベースの 1 件。id・名前・説明・親タグ・同義語）と `SelectedTag`（`select_tags` の結果 1 件。id・名前・score・path）。`TagMetadataRepository`・各エンジン・MCP ツールで使う。 |
