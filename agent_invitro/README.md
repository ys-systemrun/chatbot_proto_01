# agent_invitro — Conversation Agent（LangGraph MCPホスト実験）

社内QAチャットボットの「対話エージェント」を、LangGraph の ReAct エージェントとして構築する実験用コンポーネントです。ユーザーの質問に対し、2つの MCP サーバー（Tag Selector MCP / Knowledge MCP）が公開するツールを LLM が自律的に呼び出して回答を生成します。

- 文書番号: IMPL-202608061725
- 参照: 要件定義書 `docs/requirement/202608061621.md`、ADR `docs/adr/0019〜0022`
- 位置づけ: **実験用 MVP**。精度・レイテンシの定量評価は対象外。常駐 HTTP サーバー化はせず、`docker compose exec` で IPython を起動して対話的に動作確認する。

## 全体像

```
ユーザーの質問
    │
    ▼
┌─────────────────────────────┐
│  agent_invitro (ReActエージェント)  │  ← LangGraph create_react_agent
│  LLM = LM Studio (OpenAI互換API)    │  ← langchain-openai ChatOpenAI
└───────────────┬─────────────┘
                │ MCP (streamable_http) ※langchain-mcp-adapters
        ┌───────┴────────┐
        ▼                ▼
  tag_selector_mcp   knowledge_mcp
   (select_tags)    (search_knowledge)
```

質問を受けると、LLM は概ね次の順でツールを呼びます（システムプロンプトで誘導。ReActのため厳密な順序保証はなし）。

1. `select_tags`（tag_selector_mcp）— 質問文に関連するタグを取得
2. `search_knowledge`（knowledge_mcp）— タグを使って社内QAを検索
3. 検索結果をもとに回答を生成。関連情報が無ければ「関連する情報が見つかりませんでした」と返す（推測で作らない）

## HTTP エンドポイント（AWS 環境）

AWS 環境では Uvicorn で `agent_invitro.main.api.server:app` を起動し、`admin_ui` からの VPC 内部
通信を受けます（ALB からの到達性は与えない, ADR-0023 / ADR-0043 / ADR-0045）。ローカル
`docker-compose` は `sleep infinity` のままで、HTTP サーバーは起動しません（ADR-0019）。

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/health` | プロセス生存確認のみ（DB・MCP への到達性は見ない） |
| POST | `/ask-pipeline` | 単発プロンプト生成方式。言い換え → タグ選定 → 検索1回 → 回答生成（ADR-0043） |
| POST | `/ask-agentic` | Agentic 探索ループ。言い換え → タグ選定 →（検索 → 十分性評価）を最大2周回 → 回答生成 or 逆質問（ADR-0088） |

`/ask-pipeline` と `/ask-agentic` のリクエスト・レスポンスのスキーマは完全に同一です
（ADR-0089 決定2）。探索の経過はレスポンスに含めず、`logger.info` でのみ出力します（同 決定4）。

```
        [start]
           │
      condense           … condensed_query 生成（ADR-0085、1回のみ）
           │
     select_tags         … タグ選定（ADR-0086、1回のみ）
           │
           ▼
    ┌── search ◀────────────────┐   … search_knowledge 1回（query は周回ごとに変わる）
    │      │                    │
    │   assess                  │   … 十分性評価 LLM（sufficient / missing / next_query）
    │      │                    │
    │      ├─ sufficient ──────────────▶ generate ─▶ [end]
    │      ├─ 不十分 & 周回数 < 上限 ──┘（next_query で再検索）
    │      └─ 不十分 & 周回数 = 上限
    │              ├─ 蓄積結果あり ────▶ generate ─▶ [end]   … ベストエフォート回答
    └──────────────┴─ 蓄積結果が空 ────▶ clarify  ─▶ [end]   … 逆質問
```

十分性評価・逆質問生成が失敗しても 500 にはならず、`/ask-pipeline` と同等（検索1回＋回答生成）へ
縮退します（ADR-0088 決定7）。

## ディレクトリ・ファイル構成

```
agent_invitro/
├── Dockerfile                         … sleep infinity で常駐（ローカルは HTTPサーバを起動しない）
├── pyproject.toml                     … 依存: langgraph / langchain-mcp-adapters / langchain-openai
│                                          / langchain-aws / ipython / fastapi / uvicorn
├── README.md
├── src/                              … Python パッケージ名は agent_invitro（pyproject.toml の package-dir で対応付け）
│   ├── __init__.py
│   ├── config.py                     … 環境変数の読み込み・Settings の保持
│   ├── llm.py                        … Chat モデルのビルダー・URL変換（to_openai_base_url）
│   ├── condense.py                   … 言い換え質問（condensed_query）生成 LLM（ADR-0085）
│   ├── summarize.py                  … 会話履歴の要約 LLM（ADR-0043）
│   ├── generate.py                   … 回答生成 LLM（ADR-0043。両エンドポイントで共有）
│   ├── clarify.py                    … 逆質問生成 LLM（ADR-0088）
│   ├── tags.py                       … select_tags の戻り値パース・alias_match_text 構築（ADR-0086）
│   ├── knowledge.py                  … search_knowledge 呼び出し・結果パース・蓄積の重複排除（ADR-0090）
│   ├── llm_tasks/                    … LLM機能モジュール群（ADR-0091。機能ごとにサブパッケージ）
│   │   └── assess/                   … 十分性評価（ADR-0088 / ADR-0091）
│   │       ├── base.py               … SufficiencyAssessor（抽象基底クラス）・縮退値
│   │       ├── parsing.py            … parse_assessment（純関数）
│   │       ├── prompts.py            … システムプロンプト・ユーザーメッセージ構築
│   │       └── bedrock.py            … SufficiencyAssessorBedrock（Converse API・縮退処理）
│   ├── mcp_clients/
│   │   └── client.py                 … MultiServerMCPClient のセットアップ・ツール取得
│   ├── graph/
│   │   ├── agent.py                  … ReActエージェント構築・システムプロンプト（IPython 実験用途）
│   │   └── agentic_search.py         … Agentic 探索ループの StateGraph（ADR-0088）
│   ├── usecases/                     … ユースケース層（fastapi に依存しない実処理, ADR-0090）
│   │   ├── conversation.py           … 要約畳み込み・history/next_order 算出・context 構築（共通）
│   │   ├── ask_pipeline.py           … /ask-pipeline の実処理（単発プロンプト生成方式）
│   │   └── ask_agentic.py            … /ask-agentic の実処理（Agentic 探索ループ）
│   └── main/                         … エントリポイント群
│       ├── api/
│       │   ├── server.py             … 起動エントリポイント。create_app() を呼び app を公開するのみ
│       │   ├── app.py                … create_app(): FastAPI 生成・router 登録・ロギング設定
│       │   ├── schemas.py            … Message / Summary / Request / Response（全エンドポイント共通）
│       │   ├── dependencies.py       … コンポーネントの遅延初期化・DI
│       │   └── routers/
│       │       ├── health.py         … GET /health
│       │       ├── ask_pipeline.py   … POST /ask-pipeline
│       │       └── ask_agentic.py    … POST /ask-agentic
│       └── ipython/
│           └── main.py               … IPython から呼び出す build() / run()（コンポジションルート）
├── scripts/
│   └── check_tool_calling.py          … Phase 1 スモークテスト（Tool Calling 対応可否の確認）
└── tests/                             … MCP・LLM 非接続で動く単体テスト
    ├── test_graph_smoke.py            … build_agent() のスモークテスト
    ├── test_config_llm.py             … load_settings / build_llm の provider 分岐
    ├── test_mcp_result_parsing.py     … MCP ツール戻り値パース（ADR-0063）
    ├── test_alias_match_text.py       … alias_match_text 構築（ADR-0086）
    ├── test_condense.py               … 言い換え質問生成（ADR-0085）
    ├── test_agentic_assess.py         … 十分性評価のパース・分岐判定・結果蓄積（ADR-0088 / ADR-0091）
    └── test_ask_usecases.py           … /ask-pipeline・/ask-agentic のユースケース（ADR-0090）
```

### 各ファイルの役割

| ファイル | 役割 | 主な関数・定数 |
|---|---|---|
| `config.py` | 環境変数を読み込み `Settings` を返す。 | `Settings`（dataclass）、`load_settings()` |
| `llm.py` | `llm_provider` に応じた Chat モデル（LM Studio の `ChatOpenAI` / Bedrock の `ChatBedrockConverse`）を構築する。LM Studio の URL 形式を ChatOpenAI 用に変換する。 | `build_llm(llm_provider, ...)`、`to_openai_base_url()` |
| `mcp_clients/client.py` | 2つの MCP サーバーへの接続設定を持つ `MultiServerMCPClient` を構築し、ツール一覧を取得する。 | `build_mcp_client(tag_selector_mcp_url, knowledge_mcp_url)`、`load_tools(client)`（async） |
| `graph/agent.py` | `create_react_agent` で ReAct エージェントを組む。呼び出し順序を誘導するシステムプロンプトを持つ。 | `SYSTEM_PROMPT`、`build_agent(llm, tools)` |
| `main/ipython/main.py` | IPython から使うエントリポイント。構築一式と1クエリ実行を提供。ツール呼び出し・応答・最終回答をログ出力する。 | `build()`（async）、`run(agent, query)`（async） |
| `condense.py` | 会話文脈から今回の発話を standalone な質問文へ言い換える（ADR-0085）。失敗時は元の発話へフォールバック。 | `CondenseQueryLLMBedrock.condense()` |
| `summarize.py` | 会話履歴の先頭 n 件を要約する（ADR-0043）。 | `SummarizeLLMBedrock.summarize()` |
| `generate.py` | 参考情報と質問から回答を生成する。両エンドポイントで共有（ADR-0088 決定8）。 | `GenerateAnswerLLMBedrock.generate()` |
| `llm_tasks/assess/` | 蓄積した検索結果で回答できるかを判定し、不足観点と次のクエリを返す（ADR-0088 / ADR-0091）。抽象基底 `SufficiencyAssessor` が「同期・例外を投げない・3キーを返す」契約を定める。失敗・パース失敗時は `sufficient=true` へ縮退。 | `SufficiencyAssessor`、`SufficiencyAssessorBedrock.assess()`、`parse_assessment()` |
| `clarify.py` | 検索結果0件時に、回答に必要な情報を1〜3点尋ねる逆質問文を生成する（ADR-0088）。 | `ClarifyQuestionLLMBedrock.clarify()`、`FALLBACK_CLARIFICATION` |
| `tags.py` | `select_tags` の戻り値パースと `alias_match_text` の構築（ADR-0063 / ADR-0086）。 | `_extract_selected_tags()`、`build_alias_match_text()` |
| `knowledge.py` | `search_knowledge` の呼び出し・結果パース・周回をまたいだ重複排除（ADR-0090）。 | `search_knowledge()`、`extract_results()`、`merge_results()` |
| `graph/agentic_search.py` | `search` → `assess` を条件付きエッジで周回させる `StateGraph`（ADR-0088）。`create_react_agent` は使わない。 | `build_agentic_search_graph()`、`_decide()` |
| `usecases/conversation.py` | 両エンドポイント共通の会話処理（要約畳み込み・`history`/`next_order` 算出・`context` 構築・前処理）。 | `fold_summary_if_needed()`、`condense_query()`、`select_tag_names()`、`build_context()` |
| `usecases/ask_pipeline.py` | `/ask-pipeline` の実処理（単発プロンプト生成方式, ADR-0043）。 | `ask_pipeline(req, components)` |
| `usecases/ask_agentic.py` | `/ask-agentic` の実処理（探索ループの起動と Response 組み立て, ADR-0088）。 | `ask_agentic(req, components)` |
| `main/api/server.py` | 起動エントリポイント。`create_app()` を呼び `app` を公開するだけ。Terraform の起動コマンドが参照するモジュールパス（`agent_invitro.main.api.server:app`）を維持するため名前を変えない（ADR-0090 決定2）。 | `app` |
| `main/api/app.py` | FastAPI を生成し router を登録する。 | `create_app()` |
| `main/api/schemas.py` | API 契約（全エンドポイント共通, ADR-0089 決定2）。 | `Message` / `Summary` / `Request` / `Response` |
| `main/api/dependencies.py` | 設定読み込み・MCP ツール取得・Bedrock クライアント生成の遅延初期化と DI（ADR-0090 決定6）。 | `get_components()`（async） |
| `main/api/routers/*.py` | 薄いルーター。パス宣言・ユースケース呼び出し・例外の `HTTPException` 変換のみ（ADR-0090 決定3）。 | `router`（APIRouter） |
| `scripts/check_tool_calling.py` | ロード済みモデルが構造化 `tool_calls` を返せるかを実機確認する（Phase 1）。 | `main()` |
| `tests/test_graph_smoke.py` | モックの LLM・tools でエージェントが構築できることを確認（MCP/LM Studio 不要）。 | pytest |

### 実装上の要点

- **URL 形式の変換（`llm.to_openai_base_url`）**: 既存の `LMSTUDIO_CHAT_URL` は末尾に `/chat/completions` を含む完全URL（例 `http://host.docker.internal:1234/v1/chat/completions`）。一方 `ChatOpenAI(base_url=...)` は `.../v1` までのルートを要求する。そのまま渡すとパスが二重になりエラーになるため、必ずこの変換を経由する。
- **非同期 API**: `MultiServerMCPClient` の取得（`get_tools`）とエージェント実行（`ainvoke`）は非同期。IPython の top-level await で `await build()` / `await run(...)` の形で呼べる。通常の `python` REPL では動かない（IPython を採用した理由の一つ）。
- **API キー**: LM Studio はキーを検証しないため、ダミー文字列（`"lm-studio"`）を渡している。

## 環境変数

| 変数名 | 例 | 用途 |
|---|---|---|
| `KNOWLEDGE_MCP_URL` | `http://knowledge_mcp:8100/mcp` | Knowledge MCP への接続先 |
| `TAG_SELECTOR_MCP_URL` | `http://tag_selector_mcp:8200/mcp` | Tag Selector MCP への接続先 |
| `LMSTUDIO_CHAT_URL` | `http://host.docker.internal:1234/v1/chat/completions` | LM Studio のチャット補完エンドポイント（変換を経由して使用） |
| `LMSTUDIO_CHAT_MODEL` | （ロード済みモデル名） | チャットに使うモデル名。未指定時は docker-compose 側で `MODEL_CHAT` にフォールバック |
| `LLM_PROVIDER` | `lmstudio` | LLM 実装の切り替え。常駐 HTTP サーバー（AWS 環境）は `bedrock` のみ動作する |
| `BEDROCK_CHAT_MODEL_ID` | （モデルID） | `LLM_PROVIDER=bedrock` のとき必須。要約・言い換え・十分性評価・逆質問・回答生成で共用する |
| `BEDROCK_REGION` | `ap-northeast-1` | `LLM_PROVIDER=bedrock` のとき必須 |

`KNOWLEDGE_MCP_URL` / `TAG_SELECTOR_MCP_URL` は常に必須、`LMSTUDIO_*` / `BEDROCK_*` は
`LLM_PROVIDER` に応じて必須です。未設定なら `load_settings()` が例外を投げます。

以下は任意（未設定でも既定値で動作します）。

| 変数名 | 既定値 | 用途 |
|---|---|---|
| `TAG_SELECTOR_MAX_TAGS` | `3` | `select_tags` へ渡す最大タグ数（ADR-0057 / ADR-0086） |
| `TAG_SELECTOR_CONFIDENCE_THRESHOLD` | `0.0` | `select_tags` の確信度しきい値 |
| `AGENTIC_MAX_ITERATIONS` | `2` | `/ask-agentic` の探索ループの最大周回数（ADR-0088 決定5） |
| `AGENTIC_SEARCH_TOP_K` | `3` | `/ask-agentic` の1周回あたりの `search_knowledge` の `top_k` |

どちらの方式を使うかは、チャット画面ヘッダーの「パイプライン方式 / エージェント方式」トグルで
切り替えます（ADR-0089 決定5）。トグルは `web_backend` の `POST /api/ask-pipeline` /
`POST /api/ask-agentic` を呼び分け、`web_backend` の `agent_controller` が `agent_invitro` の
同名パスへ中継します。接続先は `web_backend` 側の `AGENT_INVITRO_BASE_URL`
（既定 `http://agent_invitro:8300`）です。

ローカル `docker-compose` では本コンテナが `sleep infinity` で HTTP サーバーを起動しないため、
上記2ルートはいずれも 502 になります。ローカルで従来の LM Studio 直接処理を試す場合は
`web_backend` の `POST /api/ask-local` を直接叩いてください。本サーバーをローカルで動かして
トグルを検証したい場合は、コンテナ内で Uvicorn を起動します。

```bash
docker compose exec agent_invitro uvicorn agent_invitro.main.api.server:app --host 0.0.0.0 --port 8300
```

なお本サーバーは `LLM_PROVIDER=bedrock` でのみ起動します（ADR-0043）。

## 使い方

### 前提

- LM Studio を起動し、`LMSTUDIO_CHAT_MODEL` のモデルをロード、`host.docker.internal:1234` で待ち受けていること
- `.env` に環境変数を設定していること（`.env.example` 参照）
- `knowledge_mcp` / `tag_selector_mcp` が healthy であること

### 1. 起動

```bash
docker compose build agent_invitro
docker compose up -d agent_invitro
```

`depends_on` により、2つの MCP サーバーが healthy になってから起動します。コンテナは `sleep infinity` で常駐します。

### 2. Phase 1: Tool Calling 対応可否の確認（最初に実施）

ロード済みモデルが構造化された `tool_calls` を返せるかを確認します。結果によって後続方針が変わるため、**最初に必ず実施**します。

```bash
docker compose exec agent_invitro python -m scripts.check_tool_calling
```

- `RESULT: 対応` → そのまま先へ進む
- `RESULT: 非対応` → いったん停止。ハンマーバッジ付きの別モデルへ切り替えるか、プロンプトベースのツール選択へ切り替えるかを発注者と協議する（実装指示書 §4.3）

### 3. 対話実行

```bash
docker compose exec agent_invitro ipython
```

IPython 内で（top-level await を利用）:

```python
from agent_invitro.main.ipython.main import build, run

# 一度だけ構築（エージェントは再利用できる）
agent, mcp_client = await build()

# 質問を投げる
await run(agent, "積算システムの操作方法を教えてください")
await run(agent, "橋梁工事の数量総括表について教えてください")
await run(agent, "今日の天気は？")  # 無関係な質問 → フォールバック回答
```

`run()` は実行中に次を標準出力へ出力し、最終回答テキストを返します。

```
[tool_call]   select_tags args={'query': '...'}
[tool_result] select_tags -> [...]
[tool_call]   search_knowledge args={'tags': [...]}
[tool_result] search_knowledge -> ...
[answer]      ...
```

### 4. 単体テスト（任意、接続不要）

```bash
docker compose exec agent_invitro pytest
```

## トラブルシューティング

- **エージェント実行中に例外**: まず `tool_calls` のパース失敗を疑う。小型モデルでは出力形式が崩れることがある。上記ログで実際の LLM 出力を確認する。
- **接続・検索の不具合**: MCP サーバー側のログを併読すると原因調査がしやすい。
  ```bash
  docker compose logs -f knowledge_mcp tag_selector_mcp
  ```
- **`langchain-mcp-adapters` の API 差異**: バージョンにより `get_tools` の引数・戻り値が変わりうる（ADR-0021）。導入バージョンのドキュメントで確認する。

## 制約（実験 MVP のため）

- 会話履歴は保持しない（1往復ごとに独立）。
- 回答の順序・内容は毎回同一にはならない（LLM の非決定性）。受け入れ基準は「実行時点での妥当性確認」を目的とする。
- ホストへのポート公開はしない（ADR-0019）。
- `select_tags` / `search_knowledge` は読み取り専用で呼ぶのみ。MCP サーバー側のデータ・実装は変更しない。
