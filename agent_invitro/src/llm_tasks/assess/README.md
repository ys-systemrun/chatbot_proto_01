# agent_invitro/src/llm_tasks/assess — 検索結果の十分性評価

`/ask-agentic` の探索ループで、これまでの検索結果で質問に回答できるかを LLM に判定させ、`sufficient` / `missing`（不足観点）/ `next_query`（次の検索クエリ）を返します（ADR-0088 決定2 / ADR-0091）。呼び出し側（`graph/agentic_search.py`・`usecases/ask_agentic.py`）は `__init__.py` の公開 API と抽象 `SufficiencyAssessor` だけに依存します。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | 公開 API（`SufficiencyAssessor`・`SufficiencyAssessorBedrock`・`parse_assessment`）を再エクスポートする。 |
| [`base.py`](base.py) | 抽象基底 `SufficiencyAssessor` と失敗時の縮退値 `DEGRADED_ASSESSMENT`（`sufficient=True`）。「同期・例外を投げない・3キーを返す」契約を定める。 |
| [`bedrock.py`](bedrock.py) | Bedrock Converse API による具象実装 `SufficiencyAssessorBedrock`。呼び出し失敗・パース失敗は縮退値で返す。 |
| [`parsing.py`](parsing.py) | LLM 出力を dict にパースする純関数 `parse_assessment()`。コードフェンスや前置きが混じっても最初の `{` から最後の `}` までを切り出して再試行する。 |
| [`prompts.py`](prompts.py) | システムプロンプト（`prompts/assess.md` を読み込む）と、質問・検索結果（本文は先頭600字に切り詰め）・試したクエリからユーザーメッセージを組み立てる `build_user_content()`。 |
