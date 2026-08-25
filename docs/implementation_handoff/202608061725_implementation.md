# Conversation Agent（LangGraph MCPホスト実験、agent_invitro）実装指示書

- 文書番号: IMPL-202608061725
- 対象プロジェクト: chatbot_invitro / `agent_invitro`
- 参照文書:
  - 要件定義書 `docs/requirement/202608061621.md`（REQ-202608061621）
  - ADR `docs/adr/0019〜0022`
  - 関連（既存）: Knowledge MCP要件定義書 `docs/requirement/202608041002.md`、Tag Selector MCP要件定義書 `docs/requirement/202608051636.md`・実装指示書 `docs/implementation_handoff/202608051712_implementation.md`
- 本書の位置づけ: 要件定義書・ADRで確定した方針を、実装担当者（開発者またはコーディングエージェント）が着手できる粒度まで具体化した指示書である。本書自体はソースコードを含まない（インターフェース仕様・作業手順・設定値の指示にとどめる）。実装は別途担当者が本書の指示に従って行うこと。

## 0. 本書作成にあたり確定した事項

要件定義書の Open Issues のうち、実装着手には確定が必要だが未決だった項目について、以下の通り値を定めた。

| 項目 | 決定内容 | 根拠・備考 |
|---|---|---|
| 配置・実行形態（ADR-0019） | 既存 `agent_invitro/` を維持し、独立Dockerコンテナだが常駐HTTPサーバー化はしない。`docker compose exec agent_invitro ipython` で対話的に動作確認する | 発注者確認済み |
| 対話シェルの実装（ADR-0019） | IPython を採用（Jupyter Labは不採用） | 発注者確認済み |
| LLM接続先（ADR-0020） | ローカルLLM（LM Studio）。既存 `LMSTUDIO_CHAT_URL` / `LMSTUDIO_CHAT_MODEL` の接続先を再利用する | 発注者確認済み |
| グラフ構造（ADR-0022） | LLMが自律的にツールを選ぶReActエージェント方式（`langgraph.prebuilt.create_react_agent` 相当） | 発注者確認済み |
| MCPクライアント実装方式（ADR-0021） | `langchain-mcp-adapters`（`MultiServerMCPClient`）を採用する。MCP公式Python SDK直接利用は不採用 | 発注者確認済み |
| 既存スカフォールドとの整合（要件定義書 Open Issue #5） | 既存 `agent_invitro/src/main/` は空であり移行コストがないため、要件定義書9.2節の構成（`src/agent_invitro/` パッケージ配下）に合わせて再編する。`src/main/` は削除する | **本書での判断**（実装コストが小さい消去法的決定のため、発注者への確認は事後報告でよいと判断） |
| 実験完了の成功条件（要件定義書 Open Issue #6） | 9章の完了条件チェックリストとして具体化した（下記10章参照） | **本書での暫定定義**。数値基準（3件中2件等）は提案値であり、実装・検証結果を見て発注者確認のうえ必要に応じて見直すこと |

残る主要Open Issueは次の1点であり、これは事前に机上で決定できるものではなく、**Phase 1（本書1章）で実機検証してから後続の実装方針を分岐させる。**

- **ロード済みLLMモデルのFunction Calling対応可否**（要件定義書 Open Issue #3）: LM Studioのモデルカタログの「ハンマー」アイコンを一次確認材料としつつ、2.1節のスモークテストで実際にOpenAI互換の `tool_calls` 形式の応答が得られるかを確認する。対応していない場合の代替方針は9章末尾の注意点を参照。

## 1. 全体進行フェーズ

| Phase | 目的 | 主な成果物 | 前提 |
|---|---|---|---|
| Phase 0 | 事前準備 | ディレクトリ雛形の再編、`pyproject.toml` | なし |
| Phase 1 | LLM前提検証 | LM StudioロードモデルのTool Calling対応可否のスモークテスト結果 | Phase 0 |
| Phase 2 | MCPクライアント層 | `MultiServerMCPClient` セットアップ、ツール取得 | Phase 1（Tool Calling対応の見込みが立った状態） |
| Phase 3 | LLM層 | LM Studio接続用のChatモデルラッパー | Phase 1 |
| Phase 4 | グラフ／エージェント層 | ReActエージェント構築、システムプロンプト | Phase 2, 3 |
| Phase 5 | エントリポイント | IPythonから呼び出す便利関数（`main.py`） | Phase 4 |
| Phase 6 | Docker統合 | Dockerfile、`docker-compose.yml`、`.env.example` 追記 | Phase 5 |
| Phase 7 | 検証・受け入れ | 手動テストクエリの実行結果、DoDチェック | Phase 6 |

後続フェーズは前フェーズの成果物を前提とするため、順序を入れ替えないこと。特にPhase 1の結果次第でPhase 4以降のプロンプト設計・受け入れ基準の解釈が変わるため、Phase 1を最優先で実施すること。

## 2. WBS（作業分解構成）

| No. | タスク | Phase | 参照 | 成果物 |
|---|---|---|---|---|
| T1 | `agent_invitro/` ディレクトリ再編（3節の構成通り、既存 `src/main/` は削除） | 0 | 0節, 要件9.2 | ディレクトリ一式 |
| T2 | `pyproject.toml` 作成（依存: `langgraph`, `langchain-mcp-adapters`, `langchain-openai`, `ipython`） | 0 | ADR-0019, 0021 | `pyproject.toml` |
| T3 | LM StudioのTool Calling対応可否スモークテストスクリプト作成・実行 | 1 | 要件6.3, Open Issue #3 | `scripts/check_tool_calling.py` と実行結果 |
| T4 | `config.py`（環境変数読み込み）実装指示 | 0 | 要件9.3 | `config.py` 相当のシグネチャ |
| T5 | `mcp_clients/client.py`（`MultiServerMCPClient` セットアップ）実装指示 | 2 | 要件6.2, ADR-0021 | `mcp_clients/client.py` 相当のシグネチャ |
| T6 | `llm.py`（LM Studio接続用Chatモデル）実装指示 | 3 | ADR-0020 | `llm.py` 相当のシグネチャ |
| T7 | `graph/agent.py`（ReActエージェント構築、システムプロンプト）実装指示 | 4 | 要件6.1, ADR-0022 | `graph/agent.py` 相当のシグネチャ |
| T8 | `main.py`（IPython向けエントリポイント）実装指示 | 5 | 要件9.1 | `main.py` 相当のシグネチャ |
| T9 | `Dockerfile` 作成指示 | 6 | ADR-0019 | Dockerfile仕様 |
| T10 | `docker-compose.yml` / `.env.example` 追記指示 | 6 | 要件9 | 差分内容 |
| T11 | 手動疎通確認（6.4節のサンプル質問でのテスト） | 7 | 要件6.4, 11章 | 確認結果 |
| T12 | DoDチェックリスト実施 | 7 | 本書10章 | チェック結果 |

## 3. ディレクトリ・ファイル構成指示（T1、要件定義書 Open Issue #5解消）

```
chatbot_invitro/
└── agent_invitro/
    ├── Dockerfile
    ├── pyproject.toml                … 依存関係定義（T2）
    ├── src/
    │   └── agent_invitro/
    │       ├── __init__.py
    │       ├── config.py              … 環境変数読み込み（T4）
    │       ├── llm.py                 … LM Studio接続用Chatモデルのビルダー（T6）
    │       ├── mcp_clients/
    │       │   ├── __init__.py
    │       │   └── client.py          … MultiServerMCPClientセットアップ・ツール取得（T5）
    │       ├── graph/
    │       │   ├── __init__.py
    │       │   └── agent.py           … ReActエージェント構築・システムプロンプト（T7）
    │       └── main.py                … IPythonから呼び出す便利関数（T8）
    ├── scripts/
    │   └── check_tool_calling.py      … Phase1スモークテスト（T3）
    └── tests/
        └── test_graph_smoke.py        … （任意）モックMCPサーバーに対するスモークテスト
```

既存の `agent_invitro/src/main/`（空ディレクトリ）は削除し、上記構成に一本化する（0節参照）。

## 4. Phase 1: LLM前提検証（T3、要件定義書 Open Issue #3）

### 4.1 一次確認: LM Studioのモデルカタログ

LM Studioアプリのモデルカタログで、現在ロード予定のチャット用モデル（`.env.example` 記載の `MODEL_CHAT`、例: `google/gemma-4-e4b`）に「ハンマー」アイコン（Native tool use support バッジ）が付いているかを確認する。付いていない場合でも次の実機検証を必ず行う（要件定義書6.3節参照）。

### 4.2 実機スモークテスト（`scripts/check_tool_calling.py`）

```python
"""
LM StudioのOpenAI互換Chat Completions APIに対し、ダミーのツール定義（tools パラメータ）を付与した
リクエストを送り、モデルが構造化された tool_calls 形式で応答できるかを確認するスモークテスト。

手順:
1. config.load_settings() で LMSTUDIO_CHAT_URL / LMSTUDIO_CHAT_MODEL を取得する。
2. llm.py の関数（T6）を用いて ChatOpenAI インスタンスを構築する。
3. 簡単なダミーツール（例: get_weather(city: str) のようなツール定義）を bind_tools() で束縛する。
4. 「東京の天気を教えて」のように、明らかにそのツールを呼ぶべき問い合わせを invoke する。
5. 返ってきた AIMessage の tool_calls 属性が空でないこと（ツール呼び出しが構造化データとして
   得られていること）を確認する。
6. 結果（対応/非対応）を標準出力に出力し、Phase 4のシステムプロンプト設計・受け入れ基準の解釈に用いる。
"""
```

### 4.3 検証結果に応じた分岐

- **対応していた場合**: Phase 2以降をそのまま進める。
- **対応していなかった場合**: 以下のいずれかを発注者と協議のうえ選択する（本書では決定できないため、Phase 2着手前に確認を得ること）。
  - LM Studioでハンマーバッジ付きの別モデル（Qwen2.5系等）を追加ロードし、`LMSTUDIO_CHAT_MODEL` を切り替える。
  - LangGraphのプロンプトベースのツール選択（`bind_tools` を使わず、システムプロンプトでツール一覧・呼び出しフォーマットを指示し、LLMの出力をパースする方式）へ切り替える。実装コストが増えるため、採用する場合は本書の6・7章の該当部分を改訂する。

## 5. インターフェース仕様（確定版）

### 5.1 `config.py`

```python
@dataclass
class Settings:
    knowledge_mcp_url: str
    tag_selector_mcp_url: str
    lmstudio_chat_url: str          # 例: http://host.docker.internal:1234/v1/chat/completions（既存形式）
    lmstudio_chat_model: str

def load_settings() -> Settings:
    """os.environ から KNOWLEDGE_MCP_URL / TAG_SELECTOR_MCP_URL / LMSTUDIO_CHAT_URL / LMSTUDIO_CHAT_MODEL
    を読み込む。未設定の必須項目があれば起動時に例外を発生させる。"""
    ...

def to_openai_base_url(chat_completions_url: str) -> str:
    """既存の LMSTUDIO_CHAT_URL は末尾に '/chat/completions' を含む完全なエンドポイント形式
    （例: http://host.docker.internal:1234/v1/chat/completions）だが、
    langchain_openai.ChatOpenAI の base_url は 'v1' までのルート（例: http://host.docker.internal:1234/v1）
    を要求する。末尾の '/chat/completions' を取り除いて返す。想定外の形式の場合は警告ログを出し、
    そのまま返す（フォールバック）。"""
    ...
```

**重要な注意（実装時の落とし穴）**: 既存 `LMSTUDIO_CHAT_URL` は tag_selector_mcp のように生HTTPリクエストで叩く用途を想定した完全URLであり、`langchain_openai.ChatOpenAI(base_url=...)` にそのまま渡すと二重に `/chat/completions` が付与されエラーになる。`to_openai_base_url()` による変換を必ず経由すること。

### 5.2 `mcp_clients/client.py`

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

def build_mcp_client(settings: Settings) -> MultiServerMCPClient:
    """Tag Selector MCP・Knowledge MCPの2サーバーへの接続設定を持つ MultiServerMCPClient を構築する。
    転送方式はいずれも streamable_http を指定する（ADR-0021、既存2サーバーの実装と一致）。

    設定イメージ:
        MultiServerMCPClient({
            "tag_selector_mcp": {"url": settings.tag_selector_mcp_url, "transport": "streamable_http"},
            "knowledge_mcp": {"url": settings.knowledge_mcp_url, "transport": "streamable_http"},
        })
    """
    ...

async def load_tools(client: MultiServerMCPClient) -> list:
    """client.get_tools() を呼び出し、select_tags（tag_selector_mcp）・search_knowledge（knowledge_mcp）
    等を含むLangChain Toolのリストを返す。呼び出しは非同期であるため、IPythonの top-level await、
    またはasyncio実行コンテキスト内で呼ぶこと。"""
    ...
```

- `langchain-mcp-adapters` のバージョンによりAPIの詳細（引数名・返り値の型）が変わる可能性があるため、実装着手時に導入予定バージョンの最新ドキュメント・型定義を確認すること（ADR-0021参照）。

### 5.3 `llm.py`

```python
from langchain_openai import ChatOpenAI

def build_llm(settings: Settings) -> ChatOpenAI:
    """LM StudioのOpenAI互換Chat Completions APIへ接続する ChatOpenAI インスタンスを構築する。
    - base_url: to_openai_base_url(settings.lmstudio_chat_url)
    - model: settings.lmstudio_chat_model
    - api_key: LM Studioはキーを検証しないため、任意のダミー文字列（例: "lm-studio"）を指定する
    - temperature 等のハイパーパラメータは詳細設計フェーズで調整してよい
    """
    ...
```

### 5.4 `graph/agent.py`

```python
from langgraph.prebuilt import create_react_agent

SYSTEM_PROMPT = """
あなたはユーザーからの質問に答えるアシスタントです。以下の方針に従ってください。

1. まず select_tags を使って質問文に関連するタグを取得してください。
2. 取得したタグを使って search_knowledge を呼び出し、関連する社内QA情報を検索してください。
3. 検索結果に基づいて、質問に対する回答を生成してください。
4. select_tags が関連タグを返さなかった場合や、search_knowledgeの検索結果が空だった場合は、
   その旨を踏まえて「関連する情報が見つかりませんでした」等の回答を返してください。
   存在しない情報を推測で作り出さないでください。
"""
# 6.1節で残存リスクとして記録した「LLMが期待順序で呼ばない可能性」への一次的なガードレールとして、
# システムプロンプトで呼び出し順序を明示する（要件定義書 Open Issue #6）。

def build_agent(llm, tools):
    """create_react_agent(llm, tools, prompt=SYSTEM_PROMPT) 相当でReActエージェントを構築する。"""
    ...
```

### 5.5 `main.py`（IPython向けエントリポイント）

```python
async def build():
    """settings, mcp_client, tools, llm, agent を構築し、(agent, mcp_client) を返す。
    IPythonの対話シェルから次のように呼び出す想定（ADR-0019、IPythonのtop-level await機能を利用）。
    ※現在のimportパスは `from agent_invitro.main.ipython.main import build, run`（後日 main/ipython/ 下へ移設）。

        from agent_invitro.main.ipython.main import build, run
        agent, mcp_client = await build()
        await run(agent, "積算システムの操作方法を教えてください")
    """
    ...

async def run(agent, query: str) -> str:
    """agent.ainvoke({"messages": [("user", query)]}) を呼び出す。
    実行中に呼ばれたツール名・引数・ツール応答、および最終回答を標準出力へログ出力する（要件定義書6.5節）。
    最終回答のテキストを返り値として返す。"""
    ...
```

## 6. 設定・環境変数一覧（確定表）

| 変数名 | 例 | 用途 |
|---|---|---|
| KNOWLEDGE_MCP_URL | http://knowledge_mcp:8100/mcp | Knowledge MCPサーバへの接続先（既存変数を再利用） |
| TAG_SELECTOR_MCP_URL | http://tag_selector_mcp:8200/mcp | Tag Selector MCPサーバへの接続先（新規） |
| LLM_PROVIDER | lmstudio | エージェント用LLM実装の切り替え（実験フェーズは`lmstudio`のみ実装） |
| LMSTUDIO_CHAT_URL | http://host.docker.internal:1234/v1/chat/completions | LM Studioのチャット補完APIエンドポイント（既存変数を再利用。5.1節の変換を経由して使用） |
| LMSTUDIO_CHAT_MODEL | （LM Studioにロード済みのモデル名） | チャット補完に使用するモデル名（既存`tag_selector_mcp`用の値を再利用する想定） |

`.env.example` に `TAG_SELECTOR_MCP_URL` を追記すること（他の変数は既存のものを再利用する）。

## 7. `docker-compose.yml` 変更指示（差分）

```yaml
  agent_invitro:
    build: ./agent_invitro
    container_name: chatbot_agent_invitro
    environment:
      - KNOWLEDGE_MCP_URL=${KNOWLEDGE_MCP_URL:-http://knowledge_mcp:8100/mcp}
      - TAG_SELECTOR_MCP_URL=${TAG_SELECTOR_MCP_URL:-http://tag_selector_mcp:8200/mcp}
      - LLM_PROVIDER=${LLM_PROVIDER:-lmstudio}
      - LMSTUDIO_CHAT_URL=${LMSTUDIO_CHAT_URL}
      - LMSTUDIO_CHAT_MODEL=${LMSTUDIO_CHAT_MODEL:-${MODEL_CHAT}}
    tty: true
    stdin_open: true
    command: ["sleep", "infinity"]
    volumes:
      - ./agent_invitro:/app
    depends_on:
      knowledge_mcp:
        condition: service_healthy
      tag_selector_mcp:
        condition: service_healthy
```

- **要件定義書9.1節のイメージからの修正点**: `tty: true` だけではコンテナのメインプロセスが存在せず、`docker compose up` 後にコンテナがすぐ終了してしまう。`command: ["sleep", "infinity"]`（フォアグラウンドで永久に待機するプロセス）を追加し、`docker compose exec agent_invitro ipython` で接続できる状態を維持する。`stdin_open: true` も、`exec` 時の対話入力を安定させるため付与する。
- 既存 `web_backend` / `frontend` / `db_hiroba_qa` / `db_hiroba_qa_init` / `knowledge_mcp` / `tag_selector_mcp` / `conversation_db` サービス定義には変更を加えない。
- ホスト側への `ports` 公開は行わない（ADR-0019）。

## 8. 実装順序と依存関係（再掲・詳細化）

1. T1・T2（雛形再編・依存定義） → **T3（LLM前提検証、必ず最初に実施し、結果次第でPhase 2以降の方針を確認する）** → T4（config） → T5（MCPクライアント）・T6（LLM）は並行可 → T7（グラフ、T5・T6完了後） → T8（エントリポイント、T7完了後） → T9・T10（Docker統合） → T11・T12（検証）。
2. T3で「対応していない」と判定された場合、T7着手前に発注者へ確認し、4.3節の代替方針のいずれを採るか決定を得ること。決定なしにT7へ進まないこと。

## 9. テスト・検証指示（Phase 7、T11・T12）

### 9.1 手動疎通確認（要件定義書6.4節のサンプル質問を使用）

`docker compose exec agent_invitro ipython` で接続し、5.5節の `build()` / `run()` を用いて以下を確認する。

| # | 質問文 | 確認内容 |
|---|---|---|
| 1 | 「積算システムの操作方法を教えてください」 | `select_tags` → `search_knowledge` の順にツールが呼ばれ、Knowledge MCPの検索結果に基づく回答が生成される |
| 2 | 「橋梁工事の数量総括表について教えてください」 | 同上 |
| 3 | 「今日の天気は？」（既存タグに無関係な質問） | エラーで停止せず、5.4節のシステムプロンプットに従い「関連する情報が見つかりませんでした」等の回答が返る |

- ツール呼び出しのログ（呼ばれたツール名・引数・順序）を必ず出力し、期待順序との一致・不一致を目視で確認する。
- 質問1・2でLLMが期待順序と異なる呼び出しをした場合でも、最終回答の内容が妥当であれば直ちに不合格とはしない（6.1節の残存リスクとして許容範囲内と扱う）。ただし、`select_tags` を一度も呼ばずに回答した場合や、明らかに無関係なタグ・検索結果に基づいて回答した場合は不合格とする。

### 9.2 単体テスト観点（`tests/test_graph_smoke.py`、任意）

- モックのMCPサーバー、またはモックの `tools` リストを用いて `build_agent()` が正しくエージェントを構築できることを確認する（実際のMCPサーバー・LM Studioへの接続を必要としない範囲での確認）。

## 10. 完了条件（要件定義書11章のDoDに対応する実装レベルの確認項目、Open Issue #6の具体化）

- [ ] Phase 1のスモークテスト（4章）を実施し、対応可否の結果を記録する。
- [ ] `agent_invitro` コンテナが `docker compose up` で起動し、`knowledge_mcp` / `tag_selector_mcp` の healthy 後に起動する。
- [ ] `docker compose exec agent_invitro ipython` で対話シェルに接続でき、`build()` / `run()` が実行できる。
- [ ] 9.1節の質問1・2について、2件中2件で `select_tags` → `search_knowledge` の呼び出しとKnowledge MCPの検索結果に基づく回答が確認できる（提案値。1件のみ成功の場合は、失敗した質問の原因（プロンプト・ツールスキーマ・モデルの限界等）を記録した上で発注者と対応方針を協議する）。
- [ ] 9.1節の質問3について、エラーで停止せず適切なフォールバック回答が返る。
- [ ] ADR-0021（`langchain-mcp-adapters` の採用）が実装検証を通じて妥当だったことを確認する（不都合が判明した場合はADR-0021を改訂する）。

MVPの受け入れ基準には、精度評価・レイテンシの定量評価は含めない（要件定義書と同様の方針）。

## 11. 実装時の注意点・落とし穴

- **`LMSTUDIO_CHAT_URL` の形式差異**: 5.1節参照。既存の完全URL形式を `langchain_openai.ChatOpenAI` の `base_url` にそのまま渡すと二重パスになりエラーとなる。変換関数を必ず経由すること。
- **`docker-compose.yml` のコンテナ維持**: 7章参照。`tty: true` のみではコンテナが起動後すぐ終了する。`command: ["sleep", "infinity"]` を追加すること。
- **MCPクライアントの非同期実行**: `MultiServerMCPClient` およびLangGraphのエージェント実行（`ainvoke`）は非同期APIである。IPythonの対話シェルではtop-level awaitがサポートされているため `await run(...)` の形でそのまま呼べるが、通常の `python` REPLでは動作しない点に注意（ADR-0019でIPythonを採用した理由の一つでもある）。
- **LM StudioのTool Calling出力の不安定さ**: LM Studioのハンマーバッジ付きモデルであっても、小型モデルでは `tool_calls` の出力形式が崩れる場合がある（要件定義書6.3節）。エージェントの実行中に例外が発生した場合、ツール呼び出しのパース失敗が原因である可能性を最初に疑い、ログ（9.1節）で実際のLLM出力を確認すること。
- **ReActエージェントの自律性に伴う挙動のばらつき**: 同じ質問文でも、LLMの応答は毎回完全に同一にはならない（温度パラメータやモデルの非決定性による）。9.1節の受け入れ基準は「毎回必ず同じ挙動になる」ことを求めるものではなく、実行時点での妥当性確認を目的とする。
- **既存2 MCPサーバーへの影響がないこと**: `agent_invitro` は `select_tags` / `search_knowledge` を読み取り専用で呼び出すのみであり、Knowledge MCP・Tag Selector MCP側の実装・データへの変更は行わない。動作確認中に両サーバーのログ（`docker compose logs knowledge_mcp` / `docker compose logs tag_selector_mcp`）を併せて確認すると、原因調査がしやすい。

## 12. 実装着手前に確認をお願いしたい事項（再掲）

本書0節の内容（配置・実行形態、対話シェル、LLM接続先、グラフ構造、MCPクライアント実装方式）は、いずれも発注者により確認・承認済みであり、実装着手可能な状態にある。

既存スカフォールドの再編（0節）は本書での判断とし、事後報告とする。実験完了の成功条件（0節・10章）は本書での暫定提案であり、実装・検証の実測値を踏まえて必要に応じて見直すことを想定している。

残る主要事項（実装ブロッカーではないが、Phase 1の結果次第で対応が必要になる可能性がある）:

- **ロード済みLLMモデルのFunction Calling対応可否**（要件定義書 Open Issue #3、本書4章）: Phase 1で実機検証し、非対応と判明した場合は4.3節の代替方針について発注者と協議のうえ決定する。
