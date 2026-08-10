# ADR-0031: AWS環境におけるLLM接続先をAmazon Bedrockへ切り替える（チャット・エンベディング）

- ステータス: Accepted
- 日付: 2026-08-10
- 関連: `docs/requirement/202608100910_MCPサーバークライアントAWSデプロイ要件定義書.md`, `docs/implementation_handoff/202608101542_implementation.md`, ADR-0012, ADR-0020, ADR-0023

## コンテキスト

実装指示書（IMPL-202608101542）の作成過程で、次の課題が判明した。`tag_selector_mcp`のチャット用LLM（ADR-0012）・`agent_invitro`のチャット用LLM（ADR-0020）、および`db_hiroba_qa_init`・`knowledge_mcp`等が利用するエンベディング用LLM（`LMSTUDIO_EMBEDDING_URL`/`MODEL_EMBEDDING`）は、いずれも発注者のローカル環境で稼働するLM Studioに依存している。ADR-0023により「オンプレ社内LANとAWS VPC間の新規接続は本フェーズでは構築しない」ことが確定しているため、AWS上のECSタスクからこのLM Studioへ到達することは、この前提と矛盾し、事実上できない。

対応方針として次の3案を提示していた（IMPL-202608101542 12章）。

1. **Amazon Bedrockへ切り替える**: チャット・エンベディングともに、AWSのマネージドLLM/埋め込みサービスであるBedrockを利用する。
2. **LM Studioへの到達性を確保する**: VPN等の追加接続を設ける。
3. **OpenAI等の外部APIへ切り替える**。

発注者より、**案1（Amazon Bedrockへの切り替え）**を採用する方針が示された。

## 決定

**AWS環境（本デプロイ）における`tag_selector_mcp`・`agent_invitro`のチャット用LLM、および`db_hiroba_qa_init`・`knowledge_mcp`等が利用するエンベディング用LLMは、いずれもAmazon Bedrockへ切り替える。**（発注者確認済み）

- **チャット**: Bedrock Converse API対応モデル（Anthropic Claude等、Tool Use/Function Calling対応）を利用する。具体的なモデルの選定は実装フェーズで確定する。
- **エンベディング**: Bedrockが提供する埋め込みモデル（Amazon Titan Text Embeddings V2、Cohere Embed Multilingual等、日本語を含む多言語対応のモデルを優先候補とする）を利用する。既存の`EMBEDDING_VECTOR_DIM`によるベクトル次元のパラメータ化（ADR-0017）の仕組みをそのまま活用し、選定した埋め込みモデルの出力次元に合わせて値を設定する。
- **認証**: APIキー管理は不要とし、ECSタスクロール（IAM）にBedrock呼び出し権限（`bedrock:InvokeModel`・`bedrock:InvokeModelWithResponseStream`等）を付与する（要件定義書6.6節の既定方針をそのまま適用する）。

## 検討した代替案

- **案2（LM Studioへの到達性確保）**: ADR-0023が確定した「オンプレ-AWS間の新規接続を構築しない」という方針と矛盾するため不採用とした。
- **案3（OpenAI等の外部API）**: Bedrockと同様にAPIキー管理・外部ネットワーク到達性（NAT/VPCエンドポイント経由）が必要になる点で構成上は近いが、発注者よりBedrockへの切り替えが明示的に指示されたため、本ADRでは詳細な比較は行わず、Bedrock採用を決定とする。

## 結果・影響

- **アプリケーションコードの変更が必要になる**: `tag_selector_mcp`・`agent_invitro`のLLM呼び出し部分、および`db_hiroba_qa_init`（・`web_backend`のクエリ時エンベディング計算部分）のエンベディング呼び出し部分について、LM Studio（OpenAI互換API）向けの実装からBedrock向けの実装への変更が必要になる。これは本デプロイ（Terraformによるインフラ構築・動作検証）のスコープを超える、アプリケーションコード自体の変更であり、本ADR・既存のIMPL-202608101542の対象外である。別途、コーディング担当（開発者またはコーディングエージェント）向けの実装指示を新たに整理する必要がある。
- ADR-0012・ADR-0020（ローカルLLM採用）は、**ローカル開発環境（docker-compose）における方針としては変更しない**。本ADRはAWS環境限定の決定であり、ローカル開発フロー（LM Studioを使った開発）には影響しない。
- Bedrockのモデルアクセスは、AWSアカウント・リージョンごとに有効化申請が必要な場合がある。実装時にAWSコンソールでモデルアクセスの有効化状況を確認すること。
- Tool Calling対応の観点では、Bedrock Converse API対応モデル（Claude等）を使うことで、`agent_invitro`のIMPL-202608061725が課題としていた「ロード済みLLMモデルのFunction Calling対応可否」（旧要件定義書 Open Issue #3）は、ローカルの小型モデルよりも安定して解決される可能性が高い。ただし実機検証は別途必要である。
- エンベディングモデルの切り替えに伴い、`EMBEDDING_VECTOR_DIM`の値が既存ローカル環境（768または384）とは異なる値になる可能性がある。既存ローカル環境のデータとAWS環境のデータは次元が異なり互換性がないため、AWS環境では`db_hiroba_qa_init`による再シード（ADR-0026, 0030で確定済みの方針）が前提となる。
- 要件定義書6.5節・6.6節のTerraformモジュール（ECSタスクロールのIAM権限）に、Bedrock呼び出し権限の付与を反映する（要件定義書側は元々「Bedrock利用時」を想定済みの記述であり、本ADRにより「利用する」ことが確定した）。
