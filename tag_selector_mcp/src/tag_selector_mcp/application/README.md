# tag_selector_mcp/src/tag_selector_mcp/application — タグ選択の処理

`select_tags` ツールの処理本体です。同義語辞書との一致で確定タグと候補を集め（Retrieval）、LLM で関連タグを選ぶ（Inference）2 段構成です（ADR-0009）。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`select_tags.py`](select_tags.py) | `SelectTagsUseCase`。`RetrievalEngine` → `InferenceEngine` を順に呼ぶユースケース。同義語照合には `alias_match_text`（省略時は `query`）、LLM 推論には `query` を使う（ADR-0086）。`mcp/tools.py` の `select_tags` から呼ばれる。 |
| [`retrieval_engine.py`](retrieval_engine.py) | `RetrievalEngine` と `RetrievalResult`。同義語が文中に含まれるタグを「確定タグ」、全タグを「候補」として返す（MVP では埋め込みによる絞り込みなし）。 |
| [`inference_engine.py`](inference_engine.py) | `InferenceEngine`。質問文・確定タグ・候補タグからプロンプトを作って LLM に渡し、JSON 応答を `SelectedTag` に変換する。確定タグを優先し、`confidence_threshold` 未満の除外と `max_tags` 件への絞り込みを行い、パースに失敗したら LLM 分は空にする。 |
