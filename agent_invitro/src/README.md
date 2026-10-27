# agent_invitro/src — Python パッケージ `agent_invitro` 本体

対話エージェントのソースコードです。`pyproject.toml` の `package-dir` でこのフォルダが `agent_invitro` パッケージに対応付けられ、`agent_invitro.main.api.server:app`（AWS 環境の常駐 HTTP サーバー）や `agent_invitro.main.ipython.main`（IPython 実験）として import されます。直下には LLM 呼び出し・MCP 戻り値の処理などの共有モジュールを置き、層ごとのものはサブパッケージに分けています（ADR-0090 / ADR-0091）。

## 構成

| 名前 | 説明 |
|---|---|
| [`graph/`](graph/README.md) | LangGraph のグラフ定義。IPython 用の ReAct エージェントと、`/ask-agentic` の探索ループ（ADR-0022 / ADR-0088）。 |
| [`llm_tasks/`](llm_tasks/README.md) | 実装を差し替えうる LLM 機能のサブパッケージ群。現在は十分性評価 `assess/` のみ（ADR-0091）。 |
| [`main/`](main/README.md) | エントリポイント群。FastAPI の HTTP サーバー（`api/`）と IPython 用（`ipython/`）。 |
| [`mcp_clients/`](mcp_clients/README.md) | Tag Selector MCP・Knowledge MCP へ接続する `MultiServerMCPClient` の構築とツール取得（ADR-0021）。 |
| [`usecases/`](usecases/README.md) | `/ask-pipeline`・`/ask-agentic` の実処理と共通の会話処理。FastAPI に依存しない（ADR-0090）。 |
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`bedrock_client.py`](bedrock_client.py) | bedrock-runtime の boto3 クライアントを生成する `make_bedrock_client()`。用途（`short` / `generate`）ごとに読み取りタイムアウトを短くし、切れた接続を再利用して ALB の 504 になるのを防ぐ。値は `BEDROCK_*_TIMEOUT_SEC` 等の環境変数で上書き可（ADR-0102）。各 `*LLMBedrock` クラスから使う。 |
| [`clarify.py`](clarify.py) | 探索しても検索結果が0件のときの逆質問文を Bedrock で生成する `ClarifyQuestionLLMBedrock`。失敗時は `FALLBACK_CLARIFICATION`（`prompts/generate.md` ルール3と同文）へ戻す（ADR-0088）。 |
| [`condense.py`](condense.py) | 要約・未要約履歴・今回の発話から、単体で意味が通る言い換え質問（condensed_query）を Bedrock で生成する `CondenseQueryLLMBedrock`。`select_tags`・`search_knowledge` の query に使う（ADR-0085）。 |
| [`config.py`](config.py) | 環境変数を読み込み `Settings`（dataclass）を返す `load_settings()`。必須値が無ければ例外を投げる。 |
| [`generate.py`](generate.py) | 参考情報・質問・会話履歴から回答を Bedrock で生成する `GenerateAnswerLLMBedrock`。両エンドポイントで共有（ADR-0043 / ADR-0088）。 |
| [`knowledge.py`](knowledge.py) | Knowledge MCP の `search_knowledge` 呼び出し、戻り値からの `results` 取り出し、周回をまたいだ結果の重複排除（`merge_results`）（ADR-0063 / ADR-0090）。 |
| [`llm.py`](llm.py) | `LLM_PROVIDER` に応じて Chat モデル（LM Studio の `ChatOpenAI` / Bedrock の `ChatBedrockConverse`）を構築する `build_llm()` と、LM Studio の URL を `ChatOpenAI` の base_url 形式に直す `to_openai_base_url()`（ADR-0031 / ADR-0033）。IPython 経路と `scripts/` で使う。 |
| [`prompt_store.py`](prompt_store.py) | `prompts/<名前>.md` を読み込む `load_prompt()` と、プロンプト一式の内容ハッシュ `prompts_hash()`。改行は LF にそろえ、`README.md` は除外する。置き場所は `AGENT_PROMPTS_DIR` で上書き可（ADR-0099 §3）。 |
| [`release.py`](release.py) | コード版（`GIT_COMMIT` / `GIT_DIRTY`）・`prompt_hash`・モデル ID・回答に効く設定値からリリースを組み立て、その SHA-256 先頭16桁を `release_id` とする `build_release()`（ADR-0099 §1）。`GET /release` と assistant メッセージへの付与で使う。 |
| [`summarize.py`](summarize.py) | 会話履歴の先頭 n 件を Bedrock で要約する `SummarizeLLMBedrock`。既存の要約がある場合は `summarize_with_existing` プロンプトを使う（ADR-0043）。 |
| [`tags.py`](tags.py) | MCP ツール戻り値の形式差を吸収する `_mcp_result_to_dicts`、`select_tags` の結果から選定タグを取り出す `_extract_selected_tags`、Alias 一致対象テキストを組み立てる `build_alias_match_text`（ADR-0063 / ADR-0086）。 |

※ `__pycache__/`・`*.egg-info/` は .gitignore 対象のため載せていません。
