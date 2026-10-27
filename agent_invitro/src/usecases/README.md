# agent_invitro/src/usecases — ユースケース層

HTTP（FastAPI）に依存しない実処理を置きます。`main/api/routers/` から呼ばれ、例外は変換せずそのまま送出します（ADR-0090 決定1・決定4）。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言。層の方針を docstring に記す。 |
| [`ask_agentic.py`](ask_agentic.py) | `ask_agentic(req, components)`: 言い換え → タグ選定を1回ずつ行い、`graph/agentic_search.py` の探索ループを回してから回答生成または逆質問で `Response` を組み立てる。探索の経過はログにのみ出す（ADR-0088 / ADR-0089）。 |
| [`ask_pipeline.py`](ask_pipeline.py) | `ask_pipeline(req, components)`: 要約畳み込み → 言い換え → タグ選定 → 検索1回 → 回答生成の一本道パイプライン（ADR-0043 / ADR-0085 / ADR-0086）。 |
| [`conversation.py`](conversation.py) | 両ユースケース共通の会話処理。要約畳み込み（`fold_summary_if_needed`）、`next_order`・履歴の算出、`context`・出典の構築、user/assistant メッセージ組み立て（`release_id` の付与を含む）、言い換え・タグ選定の前処理（ADR-0090 決定5）。 |
