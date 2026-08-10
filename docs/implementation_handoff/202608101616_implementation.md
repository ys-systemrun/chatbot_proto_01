# AWS環境向けLLM接続先のAmazon Bedrock切り替え 実装指示書

- 文書番号: IMPL-202608101616
- 対象プロジェクト: chatbot_invitro
- 参照文書:
  - ADR `docs/adr/0031-aws-llm-provider-bedrock.md`（ADR-0031）
  - 要件定義書 `docs/requirement/202608100910_MCPサーバークライアントAWSデプロイ要件定義書.md`（REQ-202608100910）
  - 実装指示書 `docs/implementation_handoff/202608101542_implementation.md`（IMPL-202608101542、インフラ構築側。本書はアプリケーションコード側の対）
  - 既存実装の根拠: ADR-0012（tag_selector_mcp MVP LLMプロバイダ）、ADR-0017（EMBEDDING_VECTOR_DIMのパラメータ化）、ADR-0020（agent_invitro LLM接続先）、ADR-0021（agent_invitroのMCPクライアント実装方式）
- 対象コンポーネント: `tag_selector_mcp`（LLM呼び出し部分）、`knowledge_mcp`（エンベディング呼び出し部分）、`db_hiroba_qa_init`（エンベディング呼び出し部分）、`agent_invitro`（LLM呼び出し部分）。**`web_backend`は対象外**（ローカル開発用途のためLM Studio接続を維持、ADR-0031）。
- 本書の位置づけ: ADR-0031で確定した方針を、実装担当者（開発者またはコーディングエージェント）が着手できる粒度まで具体化した指示書である。本書自体はソースコードを含まない（クラス・関数のインターフェース仕様、作業手順、設定値の指示にとどめる）。実際のコード変更は別途担当者が本書の指示に従って行うこと。

## 0. 本書作成にあたり確定した事項・前提

現状のLLM/エンベディング呼び出し箇所を実装調査した結果、以下の事実を確認した（本書の指示の前提とする）。

| コンポーネント | 現状の実装 | 呼び出し方式 |
|---|---|---|
| `tag_selector_mcp` | `infrastructure/llm/lmstudio.py`の`LMStudioLLMClient`（`LLMClient`抽象基底を実装、`complete(prompt: str) -> str`）。ファクトリ`infrastructure/llm/__init__.py::create_llm_client(provider, ...)`が既に`LLM_PROVIDER`による切り替えを想定した作りになっている（`bedrock`/`openai`は未実装のコメントのみ） | 生の`requests`によるOpenAI互換Chat Completions API呼び出し。Function/Tool Callingは使用せず、プロンプトでJSON出力を指示し呼び出し側でパースする方式（`application/inference_engine.py`） |
| `knowledge_mcp` | `mcp/server.py`内にインラインで定義された`_make_embed_fn(url, model_name)`が、`Callable[[str], list[float]]`型の`embed_fn`を生成し、`QARepository`・`QaManagementRepository`にDIで注入する | 生の`requests`によるOpenAI互換Embeddings API呼び出し |
| `db_hiroba_qa_init` | `src/embedding.py::get_embedding(url, model_name, text)`（`web_backend/src/embedding.py`から移管した単体関数、ADR-0016〜0018） | 同上（`knowledge_mcp`とほぼ同一実装だが独立したコード） |
| `agent_invitro` | `src/agent_invitro/llm.py::build_llm(settings) -> ChatOpenAI`（LangChainの`ChatOpenAI`をLM StudioのOpenAI互換エンドポイントに向ける） | LangChain経由。ReActエージェント（ADR-0022）が`bind_tools()`でツールを束縛するため、Tool Calling対応が必要 |

**本書での設計判断**（実装コストを抑えるための提案。発注者への確認は事後報告でよいと判断）:

- `tag_selector_mcp`は既存の`LLMClient`抽象化・ファクトリパターンをそのまま活かし、`BedrockLLMClient`を新設して`create_llm_client`に追加する（4.1節）。最小差分で済む。
- `knowledge_mcp`・`db_hiroba_qa_init`は、独立した抽象化レイヤーを新設せず、既存の関数（`_make_embed_fn`・`get_embedding`）内にプロバイダ分岐を追加する形にとどめる（4.2, 4.3節）。将来的に`tag_selector_mcp`と同様の抽象化に揃えることは妨げないが、本書では必須としない。
- エンベディングのプロバイダ切り替え用に、新規環境変数`EMBEDDING_PROVIDER`を導入する（既存の`LLM_PROVIDER`と対になる命名、5章）。
- `agent_invitro`は、LangChainのAWS向け公式連携パッケージ`langchain-aws`が提供する`ChatBedrockConverse`を使用し、`ChatOpenAI`と差し替える。Tool Calling（`bind_tools()`）に対応しているため、既存のReActエージェント構成（ADR-0022）への影響を最小化できる。

## 1. 全体進行フェーズ

| Phase | 目的 | 対象 | 前提 |
|---|---|---|---|
| Phase 1 | `tag_selector_mcp`のBedrock対応 | `BedrockLLMClient`実装、ファクトリ更新 | なし |
| Phase 2 | `knowledge_mcp`・`db_hiroba_qa_init`のBedrock対応 | エンベディング呼び出しのプロバイダ分岐追加 | なし（Phase 1と並行可） |
| Phase 3 | `agent_invitro`のBedrock対応 | `llm.py`の`ChatBedrockConverse`化 | なし（Phase 1, 2と並行可） |
| Phase 4 | 依存関係・環境変数の更新 | `pyproject.toml`・`.env.example`・`docker-compose.yml` | Phase 1〜3 |
| Phase 5 | 動作検証 | 各コンポーネント単体でのBedrock疎通確認 | Phase 4、IAM権限付与済み（IMPL-202608101542） |
| Phase 6 | IMPL-202608101542との統合検証 | AWS環境でのエンドツーエンド動作確認 | Phase 5、AWSインフラ構築完了 |

Phase 1〜3は独立したコンポーネントへの変更であり、並行して進めてよい。

## 2. WBS（作業分解構成）

| No. | タスク | Phase | 参照 | 成果物 |
|---|---|---|---|---|
| T1 | `tag_selector_mcp/infrastructure/llm/bedrock.py`新設（`BedrockLLMClient`） | 1 | 4.1節 | `bedrock.py` |
| T2 | `tag_selector_mcp/infrastructure/llm/__init__.py::create_llm_client`の更新（`"bedrock"`分岐追加） | 1 | 4.1節 | 差分 |
| T3 | `knowledge_mcp/mcp/server.py::_make_embed_fn`の更新（プロバイダ分岐追加） | 2 | 4.2節 | 差分 |
| T4 | `db_hiroba_qa_init/src/embedding.py::get_embedding`の更新（プロバイダ分岐追加） | 2 | 4.3節 | 差分 |
| T5 | `agent_invitro/src/agent_invitro/llm.py::build_llm`の更新（`ChatBedrockConverse`分岐追加） | 3 | 4.4節 | 差分 |
| T6 | `agent_invitro/src/agent_invitro/config.py::Settings`の拡張（Bedrock関連フィールド追加） | 3 | 4.4節 | 差分 |
| T7 | 4コンポーネントの`pyproject.toml`へ`boto3`（該当コンポーネント）・`langchain-aws`（`agent_invitro`のみ）を追加 | 4 | 6章 | 差分 |
| T8 | `.env.example`・`docker-compose.yml`への新規環境変数の追記 | 4 | 5章 | 差分 |
| T9 | 各コンポーネント単体でのBedrock疎通確認（ローカル環境からAWS認証情報を用いた一時的な確認、または後述IMPL-202608101542のAWS環境での確認） | 5 | 7章 | 確認結果 |
| T10 | AWS環境でのエンドツーエンド動作確認（IMPL-202608101542 8章と合わせて実施） | 6 | 7章 | 確認結果 |

## 3. Bedrock呼び出し方式の整理（実装方針）

Amazon Bedrockには大きく2種類のAPIがあり、モデルの種類によって使い分ける。

- **Converse API**（`bedrock-runtime`クライアントの`converse()`）: 対話（チャット）系モデル（Anthropic Claude等）向け。Tool Use（Function Calling相当）にも対応する。`tag_selector_mcp`・`agent_invitro`のチャット用途はこちらを使う。
- **InvokeModel API**（`bedrock-runtime`クライアントの`invoke_model()`）: 埋め込み（エンベディング）系モデル（Amazon Titan Text Embeddings、Cohere Embed等）はConverse APIの対象外であり、こちらを使う。リクエストボディの形式は選定したモデルにより異なる（例: Titan系は`{"inputText": text}`、Cohere系は`{"texts": [text], "input_type": "search_document"}`）。**具体的なモデル選定（要件定義書・IMPL-202608101542 Open Issue）に応じて、リクエストボディの実装を合わせること。**

認証は、ECS Fargateタスクに付与されたタスクロール（IAM、IMPL-202608101542 6章・10章）による既定の認証情報チェーンをそのまま利用する。`boto3.client("bedrock-runtime", region_name=...)`をAPIキー等の明示的な認証情報なしで生成すれば、タスクロールの権限が自動的に使われる。ローカル開発環境（web_backend、LM Studio利用）では本チェーンは使用しない。

## 4. インターフェース仕様（確定版）

### 4.1 `tag_selector_mcp/infrastructure/llm/bedrock.py`（新設、T1・T2）

```python
from tag_selector_mcp.infrastructure.llm.base import LLMClient

class BedrockLLMClient(LLMClient):
    """Amazon Bedrock Converse APIを用いてチャット補完を行うLLMClient実装。
    既存のLMStudioLLMClientと同一のインターフェース（complete(prompt: str) -> str）を満たす。

    コンストラクタ引数:
        model_id: Bedrock上のモデルID（例: Anthropic Claude系。具体的な値は
                  要件定義書・IMPL-202608101542のOpen Issueとして別途確定）
        region_name: Bedrockを呼び出すAWSリージョン

    complete(self, prompt: str) -> str:
        boto3の bedrock-runtime クライアントで converse() を呼び出し、
        messages=[{"role": "user", "content": [{"text": prompt}]}] の形で prompt を送信する。
        レスポンスの response["output"]["message"]["content"][0]["text"] を返す。
        既存のLMStudioLLMClient.complete()と同じく、呼び出し元（InferenceEngine、
        application/inference_engine.py）はプレーンテキストを受け取り、自前でJSONパースを行う
        既存ロジックをそのまま利用できるため、この関数より上位のコードは変更不要。
    """
    ...
```

`infrastructure/llm/__init__.py::create_llm_client(provider, chat_url, chat_model)`のシグネチャを拡張し、`provider == "bedrock"`の場合に`region_name`等の追加引数（`bedrock_region`）を受け取れるようにする。既存の`"lmstudio"`分岐には手を加えない。

### 4.2 `knowledge_mcp/mcp/server.py::_make_embed_fn`の更新（T3）

```python
def _make_embed_fn(
    provider: str,               # 新規引数。既定値 "lmstudio"（後方互換）
    url: str | None,             # lmstudio時のみ使用
    model_name: str,             # lmstudio時のモデル名 or bedrock時のモデルID
    bedrock_region: str | None,  # bedrock時のみ使用
) -> Callable[[str], list[float]]:
    """既存のLM Studio向け実装（requestsによるOpenAI互換Embeddings API呼び出し）に加え、
    provider == "bedrock" の場合は、boto3の bedrock-runtime クライアントで invoke_model() を
    呼び出し、選定した埋め込みモデルのレスポンス形式に応じてベクトル（list[float]）を
    抽出して返す関数を生成する。呼び出し元（QARepository, QaManagementRepository）は
    Callable[[str], list[float]] という契約のみに依存しているため、この関数の内部実装を
    差し替えるだけでよく、DI先のコードは変更不要。
    """
    ...
```

`create_server()`（同ファイル）で読み込む環境変数に、新規`EMBEDDING_PROVIDER`（既定値`lmstudio`）を追加し、`_make_embed_fn`へ渡す。

### 4.3 `db_hiroba_qa_init/src/embedding.py::get_embedding`の更新（T4）

```python
def get_embedding(
    provider: str,                # 新規引数。既定値 "lmstudio"
    url: str | None,              # lmstudio時のみ使用
    model_name: str,              # lmstudio時のモデル名 or bedrock時のモデルID
    text: str,
    bedrock_region: str | None = None,  # bedrock時のみ使用
) -> list[float]:
    """4.2節のknowledge_mcp側と同様の分岐を、db_hiroba_qa_init独自の実装として追加する
    （コード共有はせず複製する、既存のADR-0016〜0018の方針を踏襲）。
    呼び出し元（main.pyのシード処理）への影響は、呼び出し時の引数追加のみ。
    """
    ...
```

呼び出し元（`db_hiroba_qa_init/src/main.py`、シード処理内の呼び出し箇所）で、`provider`・`bedrock_region`を環境変数から読み込んで渡すよう更新する。

### 4.4 `agent_invitro`の更新（T5・T6）

`src/agent_invitro/config.py::Settings`に以下を追加する。

```python
@dataclass
class Settings:
    knowledge_mcp_url: str
    tag_selector_mcp_url: str
    llm_provider: str                    # 既存。"lmstudio" または "bedrock"
    lmstudio_chat_url: str | None = None      # lmstudio時のみ必須
    lmstudio_chat_model: str | None = None    # lmstudio時のみ必須
    bedrock_chat_model_id: str | None = None  # bedrock時のみ必須
    bedrock_region: str | None = None         # bedrock時のみ必須
```

`src/agent_invitro/llm.py::build_llm`を次のように更新する。

```python
def build_llm(settings: Settings):
    """settings.llm_provider に応じて分岐する。

    - "lmstudio": 既存実装のまま（ChatOpenAI、to_openai_base_url()経由）。
    - "bedrock": langchain_aws.ChatBedrockConverse(
                     model=settings.bedrock_chat_model_id,
                     region_name=settings.bedrock_region,
                 ) を返す。認証情報の明示指定は行わず、ECSタスクロールによる
                 既定の認証情報チェーンに委ねる（3章参照）。

    いずれの分岐で構築したモデルも、呼び出し元(graph/agent.py::build_agent)の
    bind_tools() 呼び出しに対してTool Calling対応のインターフェースを提供する
    （ChatBedrockConverseはBedrock Converse APIのTool Use機能をLangChainの
    bind_tools()規約でラップしている）。graph/agent.py側の変更は不要。
    """
    ...
```

## 5. 環境変数一覧（確定表、追加分）

| 変数名 | 対象コンポーネント | 説明 |
|---|---|---|
| `LLM_PROVIDER` | `tag_selector_mcp`, `agent_invitro` | 既存変数。AWS環境では`bedrock`を設定する（ローカル環境は引き続き`lmstudio`） |
| `EMBEDDING_PROVIDER` | `knowledge_mcp`, `db_hiroba_qa_init` | **新規**。AWS環境では`bedrock`を設定する（ローカル環境は引き続き`lmstudio`、既定値） |
| `BEDROCK_REGION` | `tag_selector_mcp`, `knowledge_mcp`, `db_hiroba_qa_init`, `agent_invitro` | **新規**。Bedrockを呼び出すAWSリージョン。IMPL-202608101542の`aws_region`（Terraform変数）と一致させる |
| `BEDROCK_CHAT_MODEL_ID` | `tag_selector_mcp`, `agent_invitro` | **新規**。チャット用Bedrockモデルの識別子。具体的な値はOpen Issue（8章） |
| `BEDROCK_EMBEDDING_MODEL_ID` | `knowledge_mcp`, `db_hiroba_qa_init` | **新規**。エンベディング用Bedrockモデルの識別子。具体的な値はOpen Issue（8章） |
| `EMBEDDING_VECTOR_DIM` | `db_hiroba_qa_init`（マイグレーション） | 既存変数。選定したBedrockエンベディングモデルの出力次元に合わせて値を変更する（ADR-0031、ADR-0017） |

`LMSTUDIO_CHAT_URL`・`LMSTUDIO_CHAT_MODEL`・`LMSTUDIO_EMBEDDING_URL`・`MODEL_EMBEDDING`はローカル環境（`lmstudio`/`EMBEDDING_PROVIDER=lmstudio`の場合）でのみ必須とし、既存のまま残す。AWS環境（IMPL-202608101542）のECSタスク定義では、`LLM_PROVIDER=bedrock`・`EMBEDDING_PROVIDER=bedrock`および上記Bedrock関連変数を設定し、`LMSTUDIO_*`系は設定不要とする。

## 6. 依存関係の追加

| コンポーネント | 追加パッケージ |
|---|---|
| `tag_selector_mcp` | `boto3` |
| `knowledge_mcp` | `boto3` |
| `db_hiroba_qa_init` | `boto3` |
| `agent_invitro` | `langchain-aws`（`boto3`は依存関係として含まれる） |

いずれも既存の`pyproject.toml`に追記する。バージョン固定の要否は実装時に判断してよい（ADR-0021のライブラリ成熟度リスクと同様の考え方で、`langchain-aws`は導入時点の最新ドキュメント・型定義を確認すること）。

## 7. 実装順序と依存関係

1. T1・T2（`tag_selector_mcp`）、T3（`knowledge_mcp`）、T4（`db_hiroba_qa_init`）、T5・T6（`agent_invitro`）は互いに独立しており、並行して進めてよい。
2. T7（依存関係追加）は各コンポーネントのT1〜T6と同時に進めてよい。
3. T8（環境変数追記）はT1〜T7完了後にまとめて行う。
4. T9（単体疎通確認）は、AWS認証情報（開発者のローカルAWS CLIプロファイル、またはIMPL-202608101542のAWS環境）を用いて、各コンポーネント単体でBedrock APIへの呼び出しが成功することを確認する。IMPL-202608101542のPhase 3（コンテナイメージビルド）着手前に完了させること。
5. T10（エンドツーエンド確認）は、IMPL-202608101542のPhase 5・6（ECSサービス起動・動作検証）と合わせて実施する。

## 8. Open Issues（実装時に確定が必要な事項）

1. **チャット用Bedrockモデルの具体的なモデルID**: `tag_selector_mcp`・`agent_invitro`共通。Anthropic Claude系を主要候補とするが、Tool Use対応・料金・レイテンシを踏まえて実装時にBedrockのモデルカタログで確定する（ADR-0031、IMPL-202608101542 11章と同一項目）。
2. **エンベディング用Bedrockモデルの具体的なモデルID**: Amazon Titan Text Embeddings V2（出力次元を256/512/1024から選択可）、またはCohere Embed Multilingual（1024次元、日本語を含む多言語対応）を主要候補とする。選定結果に応じて`EMBEDDING_VECTOR_DIM`・4.2/4.3節のInvokeModelリクエストボディ形式を確定する。
3. **Bedrockのモデルアクセス有効化**: 選定したモデルについて、AWSアカウント・リージョンでモデルアクセスが有効化されていることを実装着手前に確認する。
4. **IAM権限の付与**: 本書のコード変更が機能するには、IMPL-202608101542で指示されているECSタスクロールへの`bedrock:InvokeModel`権限付与が別途完了している必要がある（インフラ側の作業、本書の対象外）。
5. **ローカル環境での単体確認方法**: T9の単体疎通確認をローカル開発者端末から行う場合、AWS認証情報（IAMユーザーの一時的なBedrock呼び出し権限）を別途用意する必要がある。運用方法は実装時に確定する。

## 9. テスト・確認観点

- [ ] `tag_selector_mcp`: `BedrockLLMClient.complete(prompt)`が、既存の`InferenceEngine`が期待するJSON形式のテキストを返すことを確認する（プロンプト自体は変更しないため、モデル特性による出力品質の変化がないか実機で確認する）。
- [ ] `knowledge_mcp`・`db_hiroba_qa_init`: `EMBEDDING_PROVIDER=bedrock`設定時に、選定したモデルの出力次元が`EMBEDDING_VECTOR_DIM`と一致することを確認する（不一致の場合、RDSへの書き込み時にエラーになる）。
- [ ] `agent_invitro`: `LLM_PROVIDER=bedrock`設定時に、`build_agent`が構築するReActエージェントで、既存の手動テストクエリ（会話エージェント実験要件定義書6.4節）が実行でき、Tool Callingが機能することを確認する。
- [ ] ローカル環境（`LLM_PROVIDER=lmstudio`・`EMBEDDING_PROVIDER=lmstudio`）が本変更によって退行していないことを確認する（回帰確認、既存の`docker compose up`でのローカル動作）。

## 10. 実装時の注意点・落とし穴

- **Converse APIとInvokeModel APIの混同**: チャット系（`converse()`）とエンベディング系（`invoke_model()`）はAPIが異なる。埋め込みモデルに対して`converse()`を呼び出すとエラーになる（3章）。
- **エンベディングモデル切り替えに伴うベクトル次元の不一致**: `EMBEDDING_VECTOR_DIM`を選定モデルの出力次元と合わせないと、RDSへの書き込み時に次元不一致エラーが発生する（5章、ADR-0031）。
- **ローカル環境への影響を避けること**: 本書の変更はすべて「`provider`引数・環境変数による分岐追加」であり、既存の`lmstudio`分岐（デフォルト動作）を変更しないこと。ローカル開発環境（docker-compose、LM Studio）の`.env`のデフォルト値は`lmstudio`のまま維持する。
- **IAM権限が整うまでBedrock呼び出しは失敗する**: ローカル開発者端末やCI環境からBedrockへ疎通確認する場合、ECSタスクロールとは別に、実行者自身のIAM権限にBedrock呼び出し権限が必要になる。
- **`agent_invitro`の`to_openai_base_url()`はBedrock分岐では不要**: 既存のURL変換ヘルパー（IMPL-202608061725 5.1節）は`lmstudio`分岐専用のロジックであり、`bedrock`分岐では使用しない。分岐を誤って共通化しないよう注意する。

## 11. 実装着手前に確認をお願いしたい事項

- 8章のOpen Issue 1・2（チャット・エンベディング用Bedrockモデルの具体的な選定）は、実装着手前に確定することを推奨する（未確定のままでもインターフェース実装自体は進められるが、モデルIDをコード・設定に反映する最終ステップで確定が必要になる）。
- 本書の変更はIMPL-202608101542（インフラ構築）と対になっており、IAM権限（Bedrock呼び出し許可）がTerraform側で付与されていることが前提となる。両実装指示書の進行状況を合わせて管理すること。
