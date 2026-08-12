# ADR-0033: `llm.py` / `mcp_clients/client.py` の `Settings` への直接依存の排除（設定値の明示的な引数注入への変更）

- ステータス: Accepted
- 日付: 2026-08-12
- 関連: ADR-0020（agent_invitro LLM接続先）、ADR-0021（MCPクライアント実装方式）、ADR-0031（Bedrock切り替え）、`docs/implementation_handoff/202608101616_implementation.md`（IMPL-202608101616、現行の `build_llm(settings)` / `Settings` 拡張の決定元）、ADR-0032（本書と同時に決定したディレクトリ構成の平坦化）、本ADRに対応する実装指示書 `docs/implementation_handoff/202608120941_implementation.md`（IMPL-202608120941）

## コンテキスト

現状、`llm.py::build_llm(settings: Settings)` と `mcp_clients/client.py::build_mcp_client(settings: Settings)` は、いずれも `config.py` が定義する `Settings` dataclass を型としてimportし、`Settings` インスタンスをまるごと引数として受け取る実装になっている。`main.py::build()` が `load_settings()` で `Settings` を1つ構築し、それをそのまま両モジュールへ配る、という構成である。

この設計には次の課題がある。

- `llm.py` の責務はチャットモデルの構築であり、`Settings` が持つ `knowledge_mcp_url`・`tag_selector_mcp_url` など、`llm.py` にとって無関係なフィールドまで含む「設定値全体の形状」を知る必要はない。`mcp_clients/client.py` にとっての `llm_provider` 等も同様に無関係である。
- 各モジュールを単体テストする際、実際に使う1〜数個の値だけでなく、`Settings` の全フィールドを埋めたインスタンスを毎回構築する必要があり、テストの準備コストが高い（`tests/test_config_llm.py` 等）。
- `Settings` の形状変更（フィールドの追加・削除）のたびに、そのフィールドを実際には使わないモジュールまで `config.py` への import 面での結合を通じて間接的に影響を受ける構造になっている（ADR-0031でBedrock関連フィールドを `Settings` に追加した際も、影響範囲の切り分けが本来より曖昧になっていた）。
- 環境変数の読み込み（`os.environ` 参照）という実行環境依存の処理は `config.py` に閉じているが、`Settings` という具体クラスを媒介として、本来その関心事と無関係な `llm.py`・`mcp_clients/client.py` にまで染み出している。

発注者より、`llm.py` と `mcp_clients/client.py` が `Settings` に直接依存しない構成へリファクタリングし、`main.py` から必要な値を引数として各モジュールへ注入する方針が示された。

## 決定

**`llm.py` と `mcp_clients/client.py` を `config.Settings` に直接依存しない形へ変更する。** 各関数は、必要な設定値をプリミティブ型（`str` / `str | None`）の引数として個別に受け取る。`main.py`（コンポジションルート）が `load_settings()` で `Settings` を構築したうえで、フィールドを展開して各関数へ明示的に渡す。

新しい関数シグネチャ（詳細は実装指示書で確定）は次の方針とする。

- `mcp_clients/client.py::build_mcp_client(tag_selector_mcp_url: str, knowledge_mcp_url: str) -> MultiServerMCPClient`
- `llm.py::build_llm(llm_provider: str, *, lmstudio_chat_url: str | None = None, lmstudio_chat_model: str | None = None, bedrock_chat_model_id: str | None = None, bedrock_region: str | None = None)`

**あわせて、`config.py::to_openai_base_url()`（LM StudioのURL形式を `ChatOpenAI` 用に変換する純粋関数）を `llm.py` へ移動する。** この関数はLM Studio接続というLLM層固有の関心事であり、環境変数読み込みを責務とする `config.py` に置かれていたこと自体が、今回のリファクタリングと同根の設計的な結合であるため、あわせて解消する。これにより `llm.py` は `config.py` を一切importしない状態になる。

`config.py` に残る責務は「環境変数の読み込みと `Settings` の保持」のみとし、`Settings` dataclass と `load_settings()` のみを提供する。

## 検討した代替案

- **現状維持**: 発注者からの明示的な指示に反するため不採用。
- **`Settings` を具象クラスではなく、必要な属性のみを要求する狭い `Protocol`（構造的部分型）に置き換える**: 型定義上はモジュール間の結合を緩められるが、実行時に渡すオブジェクトは結局 `Settings` インスタンスであり、「呼び出し側が `Settings` の形状全体を意識せずテストできる」という単体テスト容易化の効果は得られない。今回の目的（テスト容易性の向上、モジュール間の無関係な結合の排除）に対しては、プリミティブ引数への分解のほうが直接的に効果があるため今回は不採用とするが、将来モジュールが増え引数点数が肥大化した場合の代替案として記録しておく。
- **`to_openai_base_url()` は `config.py` に残し、`llm.py` からはその関数のみ引き続きimportする（`Settings` 型への依存だけを外す）**: `Settings` という具体クラス・グローバルな設定集約オブジェクトへの依存は解消できるが、`config.py` というモジュール自体への依存は残る。今回は「特定のクラスへの依存」ではなく「モジュール間の不要な結合」全般の排除を狙い、より徹底した分離（`llm.py` への移動）を採用したが、変更範囲を最小にしたい場合の代替案として実装指示書のOpen Issueに記録し、着手前に発注者の最終確認を仰ぐ。

## 結果・影響

- `llm.py` は `config.py` を一切importしなくなる（`from langchain_openai import ChatOpenAI` 等のみに整理される）。
- `mcp_clients/client.py` も `config.py` を一切importしなくなる。
- `main.py` が `Settings` の形状を知る唯一のモジュールとなり、各モジュールへ値を展開・分配するコンポジションルートとしての役割を担う。将来、設定源を `Settings` dataclass 以外（例: 別の設定管理ライブラリ、AWS Parameter Store経由の動的取得等）に差し替える場合も、影響範囲は `main.py` と `config.py` に閉じる。
- `llm.py` / `mcp_clients/client.py` の単体テストが、`Settings` オブジェクトの構築を経由せず、必要な値だけをキーワード引数で直接渡せるようになり、テストの準備コストが下がる。既存テスト（`tests/test_config_llm.py`）の更新が必要になる。
- `to_openai_base_url()` の実装場所が `config.py` から `llm.py` へ移るため、これを参照している既存ドキュメント（IMPL-202608101616 5章の注意点、`agent_invitro/README.md`）の記述を実装指示書側で更新指示する。
- 関数のふるまい（ロジック）自体は変更しない。純粋なシグネチャ変更（引数の分解）とファイル間の関数移動のみであり、`graph/agent.py::build_agent(llm, tools)` や `main.py::run()` の実装には影響しない。
- 本変更はADR-0032（ディレクトリ構成の平坦化）と同時に実施する場合、ファイル移動後の新しいパス上で本ADRの変更を行う順序を推奨する（実装指示書1章参照）。
