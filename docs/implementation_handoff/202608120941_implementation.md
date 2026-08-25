# `agent_invitro` ディレクトリ構成の平坦化と設定値注入方式の見直し 実装指示書

- 文書番号: IMPL-202608120941
- 対象プロジェクト: chatbot_invitro / `agent_invitro`
- 参照文書:
  - ADR `docs/adr/0032-agent-invitro-flatten-src-layout.md`（ADR-0032、ディレクトリ構成の平坦化）
  - ADR `docs/adr/0033-agent-invitro-settings-injection.md`（ADR-0033、`Settings` 直接依存の排除）
  - 既存実装の根拠: `docs/implementation_handoff/202608061725_implementation.md`（IMPL-202608061725、現行ディレクトリ構成の決定元）、`docs/implementation_handoff/202608101616_implementation.md`（IMPL-202608101616、現行 `build_llm(settings)` / `build_mcp_client(settings)` シグネチャおよび `Settings` 拡張の決定元）、ADR-0019〜0022、ADR-0031
  - 関連ドキュメント（更新対象）: `agent_invitro/README.md`、`docs/adr/README.md`（ADR一覧）
- 本書の位置づけ: ADR-0032・ADR-0033で確定した方針を、実装担当者（開発者またはコーディングエージェント）が着手できる粒度まで具体化した指示書である。本書自体はソースコードを含まない（クラス・関数のインターフェース仕様、作業手順、設定値の指示にとどめる）。実際のコード変更・ファイル移動は別途担当者が本書の指示に従って行うこと。

## 0. 本書作成にあたり確認した現状（実装調査結果）

現行の `src/agent_invitro/` 配下の実装を調査した結果、以下の事実を確認した（本書の指示の前提とする）。

| ファイル | 現状のシグネチャ | `config.py` への依存 |
|---|---|---|
| `config.py` | `Settings`（dataclass）、`load_settings() -> Settings`、`to_openai_base_url(chat_completions_url: str) -> str` | ― |
| `llm.py` | `build_llm(settings: Settings)` | `from .config import Settings, to_openai_base_url` |
| `mcp_clients/client.py` | `build_mcp_client(settings: Settings) -> MultiServerMCPClient`、`load_tools(client) -> list`（async） | `from ..config import Settings`（`build_mcp_client` のみ。`load_tools` は無依存） |
| `graph/agent.py` | `build_agent(llm, tools)` | 依存なし（変更対象外） |
| `main.py` | `build()`（async）、`run(agent, query)`（async） | `load_settings()` を呼び出す唯一のモジュール（変更対象。コンポジションルートとしての役割を明確化する） |

注記: ユーザー指示では `mcp_clients/clients.py` と表記されていたが、実ファイル名は `mcp_clients/client.py`（単数形）である。本書では実ファイル名に従う。

`pyproject.toml` の現行パッケージ検出設定:

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

これは `src/agent_invitro/`（`__init__.py` を持つディレクトリ）を自動検出し、ディレクトリ名からパッケージ名 `agent_invitro` を推測する方式である。

**本書作成時点では `Dockerfile` の内容を参照できていない。** ADR-0032の「結果・影響」に記載の通り、`src/agent_invitro` への直接参照（`COPY` のサブパス指定等）がないか、実装着手時に必ず確認すること（本章末尾のチェック項目、5.4節参照）。

## 1. 全体進行フェーズ

| Phase | 目的 | 対象 | 前提 |
|---|---|---|---|
| Phase 1 | ディレクトリ構成の平坦化（ADR-0032） | ファイル移動、`pyproject.toml` 更新、パッケージング動作確認 | なし |
| Phase 2 | 設定値注入方式の見直し（ADR-0033） | `llm.py`・`mcp_clients/client.py`・`main.py` のシグネチャ変更 | Phase 1完了（新しいファイルパス上で実施するため） |
| Phase 3 | 周辺ドキュメント・テストの更新 | README、ADR一覧、既存テスト | Phase 1, 2 |
| Phase 4 | 動作検証 | IPython手動疎通確認、pytest実行 | Phase 1〜3 |

Phase 1とPhase 2は論理的には独立した変更だが、Phase 2の対象ファイルはPhase 1で物理的に移動される（`src/agent_invitro/llm.py` → `src/llm.py` 等）ため、**先にPhase 1（純粋な移動・パッケージング設定変更）を完了させ、移動後の新しいパス上でPhase 2（シグネチャ変更）を行う**順序を推奨する。1コミットにまとめて行うか、2コミットに分けるかは実装担当者の判断でよい。

## 2. WBS（作業分解構成）

| No. | タスク | Phase | 参照 | 成果物 |
|---|---|---|---|---|
| T1 | `src/agent_invitro/` 配下の全ファイルを `src/` 直下へ移動し、空になった `src/agent_invitro/` を削除 | 1 | ADR-0032, 3章 | ディレクトリ一式 |
| T2 | `pyproject.toml` のパッケージ検出設定を明示的マッピングへ変更 | 1 | 4.1節 | `pyproject.toml` 差分 |
| T3 | `pip install -e .` の再実行、`import agent_invitro` の動作確認 | 1 | 5.2節 | 確認結果 |
| T4 | `Dockerfile` / `docker-compose.yml` の `src/agent_invitro` 直接参照の点検・修正 | 1 | 5.4節 | 差分（該当時のみ） |
| T5 | `mcp_clients/client.py::build_mcp_client` のシグネチャ変更（`Settings` 除去） | 2 | 4.3節 | 差分 |
| T6 | `llm.py::build_llm` のシグネチャ変更（`Settings` 除去）、`to_openai_base_url()` の `config.py` からの移設 | 2 | 4.4節 | 差分 |
| T7 | `config.py` から `to_openai_base_url` を削除（`Settings`・`load_settings` のみ残す） | 2 | 4.4節 | 差分 |
| T8 | `main.py::build()` の呼び出し側更新（`Settings` のフィールド展開） | 2 | 4.5節 | 差分 |
| T9 | `agent_invitro/README.md` のディレクトリ構成図・関数シグネチャ記述の更新 | 3 | 6章 | 差分 |
| T10 | `docs/adr/README.md`（ADR一覧）へ ADR-0032・ADR-0033 の行を追加 | 3 | 6章 | 差分 |
| T11 | 既存テスト（`tests/test_config_llm.py`、`tests/test_graph_smoke.py`）の更新 | 3 | 7章 | 差分 |
| T12 | IPython手動疎通確認（既存3問の再実行、リグレッション確認） | 4 | 7章 | 確認結果 |
| T13 | `pytest` 実行によるリグレッション確認 | 4 | 7章 | 確認結果 |

## 3. ディレクトリ・ファイル構成（Before / After）

**Before（現行）:**

```
agent_invitro/
├── Dockerfile
├── pyproject.toml
├── README.md
├── src/
│   └── agent_invitro/
│       ├── __init__.py
│       ├── config.py
│       ├── llm.py
│       ├── main.py
│       ├── graph/
│       │   ├── __init__.py
│       │   └── agent.py
│       └── mcp_clients/
│           ├── __init__.py
│           └── client.py
├── scripts/
│   └── check_tool_calling.py
└── tests/
    ├── test_config_llm.py
    └── test_graph_smoke.py
```

**After（本書適用後）:**

```
agent_invitro/
├── Dockerfile
├── pyproject.toml                 … 4.1節の通り更新
├── README.md                      … 6章の通り更新
├── src/
│   ├── __init__.py
│   ├── config.py                  … Settings, load_settings のみ（4.4節）
│   ├── llm.py                     … build_llm + to_openai_base_url（4.4節）
│   ├── main.py                    … build() 更新（4.5節）
│   ├── graph/
│   │   ├── __init__.py
│   │   └── agent.py               … 変更なし
│   └── mcp_clients/
│       ├── __init__.py
│       └── client.py              … build_mcp_client 更新（4.3節）
├── scripts/
│   └── check_tool_calling.py      … 変更なし（ただし内部でSettings/build_llm等を使っている場合は7章参照）
└── tests/
    ├── test_config_llm.py         … 更新（7章）
    └── test_graph_smoke.py        … 変更不要見込み（7章で確認）
```

`scripts/check_tool_calling.py` は本書作成時点で内容を確認できていない。`config.load_settings()` や `llm.build_llm(settings)` を呼び出している場合、4章のシグネチャ変更に追従する必要があるため、実装時に内容を確認すること（Open Issue、8章）。

パッケージ内の相対import（`.config`、`.graph.agent`、`.mcp_clients.client` 等）は、移動後もファイル間の相対階層関係が変わらないため**変更不要**である。誤って `from .agent_invitro.config import ...` のような存在しない階層への書き換えを行わないこと。

## 4. インターフェース仕様（確定版）

### 4.1 `pyproject.toml`（T2）

現行:

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

変更後（案。setuptoolsのバージョンにより推奨記法が変わり得るため、実装時に最新ドキュメントで確認すること。8章Open Issue参照）:

```toml
[tool.setuptools]
package-dir = {"agent_invitro" = "src"}
packages = ["agent_invitro", "agent_invitro.graph", "agent_invitro.mcp_clients"]
```

- パッケージ名 `agent_invitro` を物理ディレクトリ `src` に明示的に対応付け、サブパッケージ（`agent_invitro.graph`、`agent_invitro.mcp_clients`）は `package-dir` の接頭辞ルールにより自動的に `src/graph`、`src/mcp_clients` に対応付けられる（setuptoolsの標準的な `package_dir` の挙動）。
- 自動検出（`packages.find`）は「ディレクトリ名がそのままパッケージ名になる」ことを前提とするため、`src` ディレクトリを `agent_invitro` という別名のパッケージとして扱う今回のケースには使えない。したがって `packages` は明示列挙とする。
- **運用上の注意**: 将来 `src/` 配下に新しいサブパッケージ（新規ディレクトリ＋`__init__.py`）を追加する場合、`packages` リストへの追記が必要になる（現行の自動検出では不要だった手順）。追加を忘れるとそのサブパッケージがインストール対象から漏れる。

### 4.2 ファイル移動（T1）

```
src/agent_invitro/__init__.py          → src/__init__.py
src/agent_invitro/config.py            → src/config.py
src/agent_invitro/llm.py               → src/llm.py
src/agent_invitro/main.py              → src/main.py
src/agent_invitro/graph/               → src/graph/
src/agent_invitro/mcp_clients/         → src/mcp_clients/
```

> 注: 本書の移動先 `src/main.py` は、その後エントリポイントを用途別に整理した際に `src/main/ipython/main.py`（import名 `agent_invitro.main.ipython.main`）へ再移設した。HTTP APIエントリは `src/main/api/server.py`（`agent_invitro.main.api.server`）。

移動後、空になった `src/agent_invitro/` ディレクトリ（および `__pycache__` 等のビルド副産物）を削除する。移動前に `__pycache__` を一括削除しておくと、移動後の混同を避けられる。

### 4.3 `mcp_clients/client.py`（T5）

```python
from langchain_mcp_adapters.client import MultiServerMCPClient


def build_mcp_client(tag_selector_mcp_url: str, knowledge_mcp_url: str) -> MultiServerMCPClient:
    """Tag Selector MCP・Knowledge MCPの2サーバーへの接続設定を持つ client を構築する。

    Settings オブジェクトを直接受け取らず、必要な2つのURLをプリミティブな引数として
    直接受け取る（ADR-0033）。呼び出し元（main.py）が Settings からの値の展開を行う。
    転送方式はいずれも streamable_http を指定する（ADR-0021を踏襲、既存の挙動から変更なし）。
    """
    ...


async def load_tools(client: MultiServerMCPClient) -> list:
    """変更なし。既存実装のまま（Settingsへの依存はもともと無い）。"""
    ...
```

- `from ..config import Settings` の import 文を削除する。
- 関数本体のロジック（`MultiServerMCPClient` へ渡す辞書の組み立て）自体は変更しない。`settings.tag_selector_mcp_url` / `settings.knowledge_mcp_url` を参照していた箇所を、それぞれ新しい引数 `tag_selector_mcp_url` / `knowledge_mcp_url` を直接参照する形に置き換えるのみ。

### 4.4 `llm.py`（T6・T7）

```python
"""Chat モデルのビルダー（ADR-0020, ADR-0031, ADR-0033）。

Settings オブジェクトを直接受け取らず、llm_provider に応じて必要な値を
プリミティブな引数として個別に受け取る。config.py への依存を持たない
（to_openai_base_url もconfig.pyから本ファイルへ移設、ADR-0033）。
"""

from langchain_openai import ChatOpenAI

_DUMMY_API_KEY = "lm-studio"


def to_openai_base_url(chat_completions_url: str) -> str:
    """config.py から移設（ADR-0033）。ロジックは変更しない。

    既存の LMSTUDIO_CHAT_URL は末尾に '/chat/completions' を含む完全なエンドポイント形式
    だが、ChatOpenAI の base_url は 'v1' までのルートを要求するため、末尾の
    '/chat/completions' を取り除いて返す。想定外の形式の場合は警告ログを出し、
    そのまま返す（フォールバック）。既存の config.py 版と完全に同一の実装とすること。
    """
    ...


def build_llm(
    llm_provider: str,
    *,
    lmstudio_chat_url: str | None = None,
    lmstudio_chat_model: str | None = None,
    bedrock_chat_model_id: str | None = None,
    bedrock_region: str | None = None,
):
    """llm_provider に応じた Chat モデルを構築する。

    - "lmstudio": ChatOpenAI（to_openai_base_url()経由）。lmstudio_chat_url /
                  lmstudio_chat_model を使用する。
    - "bedrock":  langchain_aws.ChatBedrockConverse。bedrock_chat_model_id /
                  bedrock_region を使用する。認証情報の明示指定は行わず、
                  既定の認証情報チェーンに委ねる（既存実装から変更なし）。

    分岐ロジック自体は現行の build_llm(settings) と同一。settings.xxx への
    アクセスを、対応する引数名への直接参照に置き換えるのみ。
    """
    ...
```

- `from .config import Settings, to_openai_base_url` の import 文を削除する（`llm.py` は `config.py` を一切importしなくなる）。
- `to_openai_base_url()` の実装内容（ロジック）は一切変更しない。定義場所を `config.py` から `llm.py` へ移すのみ。
- `config.py` 側からは `to_openai_base_url` の定義を削除する（T7）。`config.py` に残るのは `Settings` dataclass と `load_settings()` のみとなる。

### 4.5 `main.py`（T8）

```python
from .config import load_settings
from .graph.agent import build_agent
from .llm import build_llm
from .mcp_clients.client import build_mcp_client, load_tools


async def build():
    """settings, mcp_client, tools, llm, agent を構築し、(agent, mcp_client) を返す。

    main.py はSettingsの形状を知る唯一のモジュールとして、load_settings()で
    取得した値をフィールドごとに展開し、各モジュールの関数へキーワード引数として
    明示的に渡す（ADR-0033、コンポジションルート）。
    """
    settings = load_settings()

    mcp_client = build_mcp_client(
        tag_selector_mcp_url=settings.tag_selector_mcp_url,
        knowledge_mcp_url=settings.knowledge_mcp_url,
    )
    tools = await load_tools(mcp_client)

    llm = build_llm(
        llm_provider=settings.llm_provider,
        lmstudio_chat_url=settings.lmstudio_chat_url,
        lmstudio_chat_model=settings.lmstudio_chat_model,
        bedrock_chat_model_id=settings.bedrock_chat_model_id,
        bedrock_region=settings.bedrock_region,
    )
    agent = build_agent(llm, tools)
    return agent, mcp_client


async def run(agent, query: str) -> str:
    """変更なし。"""
    ...
```

`run()` は `Settings` に依存していないため変更不要。

## 5. 移行時の落とし穴・注意点

1. **パッケージング設定ミス**: 4.1節の `packages` リストへ `agent_invitro.graph` / `agent_invitro.mcp_clients` を書き漏らすと、`import agent_invitro.graph.agent` 等が `ModuleNotFoundError` になる。T3で必ず実インポート確認を行うこと。
2. **エディタブルインストールの再実行忘れ**: 開発コンテナ・開発環境で `pip install -e .` 済みの場合、レイアウト変更後に再実行しないと古いパスマッピングが残り、ファイルを更新しても反映されない・見つからない等の混乱が起きる。T3で必ず再実行する。
3. **相対importの誤修正**: 3章末尾の通り、相対importは変更不要。ファイル移動の作業中に誤って階層を深く（または浅く）書き換えないよう注意する。
4. **Dockerfile / docker-compose.yml の直接パス参照**: `Dockerfile` の `COPY` 命令や `WORKDIR`、`docker-compose.yml` のボリュームマウント（現行 `./agent_invitro:/app` 相当）に `src/agent_invitro` を直接指すサブパスがないか確認する。コンポーネントディレクトリ全体をマウント・COPYしている場合は影響なしの可能性が高いが、本書作成時点でこれらのファイルの内容を確認できていないため、**実装着手時に必ず現物を確認すること**（8章Open Issue）。
5. **`scripts/check_tool_calling.py` の追従漏れ**: 内部で `config.load_settings()` や `llm.build_llm(settings)` を呼び出している場合、4.4節のシグネチャ変更に合わせて呼び出し側を更新する必要がある。内容未確認のため実装時に確認すること（8章Open Issue）。
6. **`to_openai_base_url` の呼び出し元漏れ**: `llm.py` 内以外でこの関数を直接importしている箇所がないか（`scripts/`・`tests/` を含む）、リポジトリ全体を検索して確認すること。

## 6. ドキュメント更新指示（T9・T10）

- `agent_invitro/README.md`:
  - 「ディレクトリ・ファイル構成」節の図を3章の After 構成に更新する。
  - 「各ファイルの役割」表内の `build_llm(settings)` → `build_llm(llm_provider, ...)`、`build_mcp_client(settings)` → `build_mcp_client(tag_selector_mcp_url, knowledge_mcp_url)` に更新する。
  - `config.py` の役割説明から `to_openai_base_url()` の記載を削除し、`llm.py` の役割説明に追記する。
- `docs/adr/README.md`（ADR一覧）:
  - 表の末尾に ADR-0032・ADR-0033 の行を追加する（既存の書式に合わせる）。

## 7. テスト・検証観点（T11〜T13）

- [ ] `tests/test_config_llm.py`: 現状の内容は本書作成時点で未確認だが、`Settings` を直接構築して `build_llm(settings)` を呼んでいるテストがあれば、`build_llm(llm_provider=..., lmstudio_chat_url=..., ...)` の形（キーワード引数で必要な値のみ）に書き換える。あわせて `to_openai_base_url` のテストがあれば、import元を `config` から `llm` に更新する。
- [ ] `tests/test_graph_smoke.py`: `build_agent()` のみを対象としており `Settings`/`build_llm`/`build_mcp_client` に依存していない想定だが、実装時に内容を確認し、依存があれば追従する。
- [ ] `import agent_invitro` および `import agent_invitro.graph.agent`、`import agent_invitro.mcp_clients.client` が新しいパッケージング設定のもとで問題なく解決できることを確認する（T3）。
- [ ] `docker compose exec agent_invitro pytest` が全件成功することを確認する。
- [ ] `docker compose exec agent_invitro ipython` で接続し、`from agent_invitro.main.ipython.main import build, run` → `agent, mcp_client = await build()` → 既存の手動テストクエリ（要件定義書6.4節、IMPL-202608061725 9.1節と同一の3問）を再実行し、リグレッションがないことを確認する。
- [ ] ローカル環境（`LLM_PROVIDER=lmstudio`）・Bedrock環境（`LLM_PROVIDER=bedrock`、確認可能な場合）の双方で `build_llm` の分岐が従来通り動作することを確認する（IMPL-202608101616 9章の回帰確認に相当）。

## 8. Open Issues（実装時に確定・確認が必要な事項）

1. **`to_openai_base_url` の移設先**: ADR-0033では `llm.py` への移設を決定したが、変更範囲を最小化する代替案（`config.py` に残し `llm.py` からimportする）も許容範囲として記録している（ADR-0033 代替案）。実装着手前に発注者の最終確認を推奨する。
2. **`pyproject.toml` の確定記法**: 4.1節の `package-dir` + `packages` 明示列挙は一般的なsetuptoolsの手法だが、導入する `setuptools` のバージョンにより推奨記法（例: `packages.find` の `include`/`exclude` オプションとの組み合わせ）が異なる可能性がある。実装着手時に最新ドキュメントで確認し、`pip install -e .` 実行と `import` 確認（T3）で実際に機能することを検証すること。
3. **`Dockerfile` / `docker-compose.yml` の現物未確認**: 本書は `src/agent_invitro/` 配下のPythonファイルと `pyproject.toml`・`README.md` の内容を確認して作成したが、`Dockerfile` 自体は本書作成時点で参照できなかった（作業環境の制約による）。実装時に必ず内容を確認し、`src/agent_invitro` への直接参照がないか点検すること（5章参照）。
4. **`scripts/check_tool_calling.py` の内容未確認**: 同様に本書作成時点で内容を確認できていない。`config.load_settings()` / `llm.build_llm(settings)` を利用している場合は4章のシグネチャ変更に追従させること。
5. **`tests/test_config_llm.py` の現行テスト内容未確認**: ファイル名から `config.py` と `llm.py` を対象とした単体テストと推測されるが、本書作成時点で内容を確認できていない。7章の指示に従い、実装時に内容を確認して更新すること。

## 9. 実装着手前に確認をお願いしたい事項

- ADR-0032（ディレクトリ構成の平坦化）・ADR-0033（設定値注入方式の見直し）の方針そのものは、いずれも発注者からの明示的な指示に基づくものであり、実装着手可能な状態にある。
- 8章のOpen Issue 1（`to_openai_base_url` の移設先）は、実装コストの差が小さいため本書では「移設する」側を採用しているが、事後報告での確定でよいか、事前確認が必要かは発注者の判断を仰ぐ。
- 8章のOpen Issue 3・4（`Dockerfile`・`scripts/check_tool_calling.py` の内容未確認）は本書の完成度に関わる制約であり、実装着手時に必ず現物を確認したうえで、本書の指示と齟齬がないかを最初に検証すること。齟齬があった場合は本書を改訂する。
