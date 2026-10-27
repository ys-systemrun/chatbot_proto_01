# agent_invitro/tests — 単体テスト

MCP サーバー・LM Studio・Bedrock に接続せずに動く pytest の単体テストです。LLM 呼び出しや MCP ツールはスタブ／フェイクに差し替えます。`docker compose exec agent_invitro pytest` で実行します。

## 構成

| 名前 | 説明 |
|---|---|
| [`test_agentic_assess.py`](test_agentic_assess.py) | 十分性評価の出力パース（`parse_assessment`）、失敗時の縮退、探索ループの分岐判定（`agentic_search._decide`）、検索結果の重複排除（`knowledge.merge_results`）を検証する（ADR-0088 / ADR-0091）。 |
| [`test_alias_match_text.py`](test_alias_match_text.py) | `tags.build_alias_match_text` が今回の発話と未要約の user 発話の質問文だけを結合し、assistant 発話・要約済み履歴を除外することを検証する（ADR-0086）。 |
| [`test_ask_usecases.py`](test_ask_usecases.py) | フェイクのツール・LLM で `/ask-pipeline`・`/ask-agentic` のユースケース層（`usecases/`）を検証する。FastAPI のテストクライアントは使わない（ADR-0090）。 |
| [`test_bedrock_client.py`](test_bedrock_client.py) | bedrock-runtime クライアントの接続・読み取りタイムアウトとリトライ設定が用途（short / generate）ごとに正しく設定されることを検証する（ADR-0102）。 |
| [`test_condense.py`](test_condense.py) | 言い換え質問（condensed_query）生成のフォールバック（初回ターン・例外・空文字）や入力組み立てを検証する（ADR-0085）。 |
| [`test_config_llm.py`](test_config_llm.py) | `load_settings` と `build_llm` の `LLM_PROVIDER`（lmstudio / bedrock）分岐を、フェイクモジュール注入で検証する。 |
| [`test_graph_smoke.py`](test_graph_smoke.py) | モックの LLM・ツールで `graph.agent.build_agent()` が ReAct エージェントを構築できることを確認するスモークテスト。 |
| [`test_mcp_result_parsing.py`](test_mcp_result_parsing.py) | langchain-mcp-adapters の戻り値の各形式（dict / JSON 文字列 / bytes / タプル / テキストブロックの list）から `selected` / `results` を取り出せることを検証する（ADR-0063）。 |
| [`test_prompt_store.py`](test_prompt_store.py) | `prompts/` の各プロンプトが存在し各モジュールに読み込まれること、ハッシュ計算などプロンプト読み込みの仕様を検証する（ADR-0099 §3）。 |
| [`test_release.py`](test_release.py) | リリース（`release_id` 等）の算出と、assistant メッセージへの付与を検証する（ADR-0099 §1）。 |

※ `__pycache__/` は .gitignore 対象のため載せていません。
