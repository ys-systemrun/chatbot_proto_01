# agent_invitro/prompts — プロンプト

agent_invitro が LLM に渡すシステムプロンプトです（ADR-0099 §3）。各モジュールが起動時に
`prompt_store.load_prompt("<名前>")` で読み込みます。このファイル（README.md）は読み込みにもハッシュにも含まれません。

| ファイル | 使う処理 | 使う経路 |
|---|---|---|
| `generate.md` | 回答生成（`generate.py`） | `/ask-pipeline`・`/ask-agentic` |
| `condense.md` | 質問の言い換え（`condense.py`, ADR-0085） | 両方 |
| `summarize.md` / `summarize_with_existing.md` | 会話履歴の要約（`summarize.py`）。既存の要約がある場合は後者 | 両方 |
| `assess.md` | 検索結果の十分性評価（`llm_tasks/assess`, ADR-0088） | `/ask-agentic` |
| `clarify.md` | 逆質問の生成（`clarify.py`, ADR-0088） | `/ask-agentic` |
| `react_agent.md` | ReAct エージェント（`graph/agent.py`, ADR-0022） | IPython のみ |

## 編集するときの注意

- **ファイルの内容がそのままプロンプトになります。** 末尾の改行の有無も文面の一部です。改行コードは読み込み時に LF にそろえます。
- 編集するとリリースの `prompt_hash` と `release_id` が変わり、以降の回答・評価がその版に結び付きます。
  何を狙った変更かは `docs/improvements/` に記録してください（ADR-0099 §6）。
- `generate.md` のルール3の文言は、`clarify.py` の逆質問生成失敗時のフォールバック文言と一致させる必要があります
  （テスト `test_clarify_fallback_constant_matches_generate_rule_3` で検査）。
- 読み込み先は環境変数 `AGENT_PROMPTS_DIR` で差し替えられます（ローカルでの試行用）。
