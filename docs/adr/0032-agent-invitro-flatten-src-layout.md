# ADR-0032: `agent_invitro` のディレクトリ構成の平坦化（`src/agent_invitro/` → `src/`）

- ステータス: Accepted
- 日付: 2026-08-12
- 関連: ADR-0019（配置・実行形態）、`docs/implementation_handoff/202608061725_implementation.md`（IMPL-202608061725、現行構成の決定元）、本ADRに対応する実装指示書 `docs/implementation_handoff/202608120941_implementation.md`（IMPL-202608120941）、ADR-0033（本書と同時に決定した設定値注入方式の見直し）

## コンテキスト

`agent_invitro` のディレクトリ構成は、IMPL-202608061725（T1、要件定義書9.2節を根拠）により次のように確定していた。

```
agent_invitro/
├── pyproject.toml
├── src/
│   └── agent_invitro/
│       ├── __init__.py
│       ├── config.py
│       ├── llm.py
│       ├── mcp_clients/
│       │   └── client.py
│       ├── graph/
│       │   └── agent.py
│       └── main.py
```

これはPythonパッケージングにおける一般的な「srcレイアウト」（`<コンポーネントルート>/src/<パッケージ名>/...`）であり、`pyproject.toml` の `[tool.setuptools.packages.find] where = ["src"]` による自動検出と組み合わせて機能している。

一方、パス表記だけを見ると `agent_invitro/src/agent_invitro/...` のように「agent_invitro」というディレクトリ名が2回連続して現れ、冗長・分かりにくいという指摘があった。発注者より、`agent_invitro/src/` 配下に、現在 `agent_invitro/src/agent_invitro/` 配下にあるファイル群（`__init__.py`・`config.py`・`llm.py`・`main.py`・`graph/`・`mcp_clients/`）を直接配置する構成へ変更する方針が示された。

この変更にあたっては、物理ディレクトリ名が変わっても、コード中で使用しているPythonの import 名（`agent_invitro.xxx`、例: `from agent_invitro.main import build, run`）を変えずに済ませられるかどうかが技術的な論点になる。

> 注（後日）: エントリポイントはその後、用途別に `src/main/` 配下へ整理された（IPython用: `src/main/ipython/main.py` → `agent_invitro.main.ipython.main`、HTTP API用: `src/main/api/server.py` → `agent_invitro.main.api.server`）。これは本ADRの「平坦化」（`config.py`・`llm.py`等を`src/`直下に置く）を覆すものではなく、`src/`配下へサブパッケージを追加した変更であり、本ADR「結果・影響」で予見していた `packages` リストへの追記（後述）が実際に発生したケースにあたる。

## 決定

**ディレクトリ構成を次のように平坦化する。**

```
agent_invitro/
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── llm.py
│   ├── main.py
│   ├── graph/
│   │   ├── __init__.py
│   │   └── agent.py
│   └── mcp_clients/
│       ├── __init__.py
│       └── client.py
```

**Pythonの import 名（パッケージ名）は `agent_invitro` のまま維持する。** 物理ディレクトリが `src/agent_invitro/` から `src/` に変わっても、`pyproject.toml` のパッケージング設定を「ディレクトリ名からパッケージ名を自動推測する」方式（現行の `packages.find`）から、「パッケージ名 `agent_invitro` を物理ディレクトリ `src` に明示的に対応付ける」方式（`package-dir` マッピング＋`packages` の明示列挙）に変更することで実現する。具体的な設定内容は本ADRに対応する実装指示書（IMPL-202608120941）で確定する。

パッケージ内の相対import（`.config`、`..config`、`.graph.agent`、`.mcp_clients.client` 等）は、ファイル間の相対的な階層関係（`graph/`・`mcp_clients/` が1階層下にある、という関係）が変わらないため、変更不要である。

## 検討した代替案

- **現状維持**: 発注者からの明示的な指示に反するため不採用。
- **`src` ディレクトリ自体をパッケージ名として扱う（`import src.llm` のような形に変更する）**: ディレクトリ移動のみで完結し、`pyproject.toml` 側の特殊なマッピング設定が不要になる利点はある。しかし `src` という一般的な語をimport名として露出させるのは可読性・意図の分かりやすさの面で劣り、README・既存ADR・実装指示書内に多数存在する `agent_invitro.xxx` という記述をすべて書き換える必要が生じる。実質的な変更範囲が大きくなるため不採用。
- **コンポーネントルート自体（`agent_invitro/` ディレクトリ）を廃止し、`chatbot_invitro` 直下に `src/` を直接配置する**: `knowledge_mcp/`・`tag_selector_mcp/` など他コンポーネントがいずれも `chatbot_invitro/<コンポーネント名>/` という並列配置（ADR-0001の方針を踏襲）であるため、コンポーネントルート自体をなくすとモノレポ全体の一貫性が崩れる。今回の指示はコンポーネント内部の `src/agent_invitro/` 部分の平坦化に限定されると解釈し、コンポーネントルート（`agent_invitro/`）自体は維持する。

## 結果・影響

- 実ファイルの移動: `src/agent_invitro/` 配下の全ファイル・ディレクトリを一段上の `src/` へ移動し、空になった `src/agent_invitro/` ディレクトリを削除する。
- `pyproject.toml` のパッケージ検出設定を、ディレクトリ名の自動推測（`packages.find`）から明示的なマッピング（`package-dir` + `packages` 列挙）へ変更する。設定を誤ると、`pip install -e .` 後に `agent_invitro` パッケージが見つからない、または `graph`・`mcp_clients` が本来の `agent_invitro.graph`・`agent_invitro.mcp_clients` ではなく無関係な独立パッケージとして誤検出される、といった不具合が起こり得る。
- 明示列挙方式を採る場合、将来 `src/` 配下に新しいサブパッケージ（新規ディレクトリ）を追加するたびに `pyproject.toml` の `packages` リストへの追記が必要になる（現行の自動検出では不要だった手順が増える）。この点は運用上の留意事項として記録する。
- 既存のエディタブルインストール（`pip install -e .`）は、レイアウト変更後に必ず再実行が必要になる。再実行しない場合、変更前のディレクトリ構成を指したパスマッピングが残り、`ModuleNotFoundError` 等の分かりにくい不具合の原因になる。
- `agent_invitro/README.md` の「ディレクトリ・ファイル構成」節の図を新構成に合わせて更新する必要がある。
- `Dockerfile`・`docker-compose.yml` に `src/agent_invitro` への直接参照（`COPY` のサブパス指定等）がないか点検し、あれば併せて修正する必要がある（本ADR作成時点ではこれら2ファイルの内容を確認できていないため、実装時に必ず確認すること。実装指示書側でチェック項目として明示する）。
- 本変更はディレクトリ構成とパッケージングメタデータのみを対象とし、各モジュールの実装ロジック（関数のふるまい）自体には影響しない。ADR-0033（設定値注入方式の見直し）と同時に実施する場合、ファイル移動後の新しいパス上で ADR-0033 の変更を行う順序を推奨する（実装指示書1章参照）。
