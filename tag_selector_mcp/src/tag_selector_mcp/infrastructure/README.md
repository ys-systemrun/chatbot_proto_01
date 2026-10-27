# tag_selector_mcp/src/tag_selector_mcp/infrastructure — 外部接続の実装

`application/` から使う外部接続の実装です。LLM の呼び出しと、DB から読んだタグ知識ベースのキャッシュを置きます。

## 構成

| 名前 | 説明 |
|---|---|
| [`llm/`](llm/README.md) | LLM クライアントの抽象と実装（LM Studio / Amazon Bedrock）、`LLM_PROVIDER` で選ぶファクトリ。 |
| [`repository/`](repository/README.md) | `tag` と `tag_alias` を読み込んでメモリにキャッシュする `TagMetadataRepository`。 |
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
