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

## ディレクトリ・ファイル構成

```
agent_invitro/
├── Dockerfile                         … sleep infinity で常駐（HTTPサーバは持たない）
├── pyproject.toml                     … 依存: langgraph / langchain-mcp-adapters / langchain-openai / ipython
├── README.md
├── src/                              … Python パッケージ名は agent_invitro（pyproject.toml の package-dir で対応付け）
│   ├── __init__.py
│   ├── config.py                     … 環境変数の読み込み・Settings の保持
│   ├── llm.py                        … Chat モデルのビルダー・URL変換（to_openai_base_url）
│   ├── mcp_clients/
│   │   └── client.py                 … MultiServerMCPClient のセットアップ・ツール取得
│   ├── graph/
│   │   └── agent.py                  … ReActエージェント構築・システムプロンプト
│   └── main.py                       … IPython から呼び出す build() / run()（コンポジションルート）
├── scripts/
│   └── check_tool_calling.py          … Phase 1 スモークテスト（Tool Calling 対応可否の確認）
└── tests/
    └── test_graph_smoke.py            … build_agent() のスモークテスト（接続不要）
```

### 各ファイルの役割

| ファイル | 役割 | 主な関数・定数 |
|---|---|---|
| `config.py` | 環境変数を読み込み `Settings` を返す。 | `Settings`（dataclass）、`load_settings()` |
| `llm.py` | `llm_provider` に応じた Chat モデル（LM Studio の `ChatOpenAI` / Bedrock の `ChatBedrockConverse`）を構築する。LM Studio の URL 形式を ChatOpenAI 用に変換する。 | `build_llm(llm_provider, ...)`、`to_openai_base_url()` |
| `mcp_clients/client.py` | 2つの MCP サーバーへの接続設定を持つ `MultiServerMCPClient` を構築し、ツール一覧を取得する。 | `build_mcp_client(tag_selector_mcp_url, knowledge_mcp_url)`、`load_tools(client)`（async） |
| `graph/agent.py` | `create_react_agent` で ReAct エージェントを組む。呼び出し順序を誘導するシステムプロンプトを持つ。 | `SYSTEM_PROMPT`、`build_agent(llm, tools)` |
| `main.py` | IPython から使うエントリポイント。構築一式と1クエリ実行を提供。ツール呼び出し・応答・最終回答をログ出力する。 | `build()`（async）、`run(agent, query)`（async） |
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
| `LLM_PROVIDER` | `lmstudio` | LLM 実装の切り替え（実験フェーズは `lmstudio` のみ） |

いずれも必須（`LLM_PROVIDER` を除く）で、未設定なら `load_settings()` が起動時に例外を投げます。

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
from agent_invitro.main import build, run

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
