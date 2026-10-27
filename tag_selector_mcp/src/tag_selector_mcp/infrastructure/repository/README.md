# tag_selector_mcp/src/tag_selector_mcp/infrastructure/repository — タグ知識ベースのキャッシュ

DB のタグ情報をメモリにキャッシュするリポジトリです。Knowledge MCP の `TagRepository` が都度 DB を参照するのとは逆に、こちらはキャッシュして使います（ADR-0011）。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`tag_metadata_repository.py`](tag_metadata_repository.py) | `TagMetadataRepository`。`tag` と `tag_alias` を全件読み込んで `TagRecord` の辞書を作り、参照を 1 回の代入で差し替える（リロード中も中途半端な状態を見せない）。`load()` / `reload()`、全件取得、ID 取得、件数、同義語の部分一致検索 `find_tags_by_alias_match()` を持つ。`main.py`（起動時ロード・定期リロード）、`RetrievalEngine`、`list_taxonomy` / `reload_taxonomy` ツールから使われる。 |
