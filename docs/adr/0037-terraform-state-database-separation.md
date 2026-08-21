# ADR-0037: Terraform state分割方針 — DB実体を独立stateに分離し、destroy対象から除外する

- ステータス: Accepted
- 日付: 2026-08-17
- 関連: ADR-0026, ADR-0027, ADR-0035, ADR-0036, `docs/requirement/202608100910_MCPサーバークライアントAWSデプロイ要件定義書.md`（14章 Open Issue #7）

## コンテキスト

現在の`envs/verify`は、VPC・RDS・ECS Fargateクラスタ・3サービス・Run Taskを含む全リソースを単一のTerraform state（S3バックエンド、キー`chatbot-invitro/verify.tfstate`、ADR-0027）で管理している。README §10の運用フローでは、検証終了後のコスト管理として`terraform destroy`を実行し、RDSを含む全リソースを都度破棄する前提になっている（`modules/database`側も`deletion_protection = false`・`skip_final_snapshot = true`と、都度破棄されることを前提としたパラメータになっている）。

この運用には次の課題がある。

- RDS（Amazon RDS for PostgreSQL、ADR-0026）は、`db_hiroba_qa_init`によるマイグレーション・シード投入（ADR-0016〜0018、0030）を経て初めてQA・タグデータが揃った状態になる。`terraform destroy`のたびにRDSごと破棄すると、次回`apply`時にRDSインスタンスの新規作成・マイグレーション・シード投入（embeddingの再計算を含む）をすべてやり直す必要があり、時間・Bedrock呼び出しコストの両面で無駄が大きい（ADR-0035がembeddingキャッシュ再利用オプションを追加した背景も、この再計算コストを課題視したものである）。
- ECSサービス（`knowledge_mcp`・`tag_selector_mcp`・`agent_invitro`）は、イメージ更新やタスク定義変更に伴い`apply`・`destroy`を比較的頻繁に繰り返す対象である一方、RDSは本来もっと変更頻度の低い、永続化したいリソースである。両者が単一stateに同居していると、アプリ層の変更のためのapply/destroy操作が誤ってDB層に影響する構造的リスクを排除できない。

検討した選択肢は次の3案。

1. **DB実体を独立したTerraform root（別state）に分離し、destroy運用の対象からも外す**: `envs/verify-database`（仮称）としてRDS・DBサブネットグループ・シークレットのみを管理する独立したstateを用意し、ネットワーク（ADR-0036により外部参照）・ECS層とは別に`apply`する。README §10の`terraform destroy`は、このDB用stateには及ばない運用に変更する。
2. **単一state内で`prevent_destroy`ライフサイクルやtarget指定運用に留める**: state自体は分割せず、RDSリソースに`lifecycle { prevent_destroy = true }`を付与し、`terraform destroy`実行時はRDSモジュールを対象外にする個別destroy運用でカバーする。
3. **現状維持（都度destroy）**: RDSも含めて毎回破棄・再構築する現行運用を継続する。

## 決定

**DB実体（RDSインスタンス・DBサブネットグループ・DATABASE_URLシークレット）を、ネットワーク層・アプリケーション層とは別の独立したTerraform state（root）に分離する（案1を採用）。**

- `terraform/envs/`配下に、既存の`verify`（ECS Fargateクラスタ・3サービス・ECR・Run Task等、アプリケーション層）とは別に、DB層専用の環境ディレクトリ（例: `envs/verify-database`）を設け、独自の`backend.tf`（同一S3バケット内の別state key、ADR-0027の方式を踏襲）を持たせる。
- DB層のstateは、ADR-0036で参照する既存VPC・既存サブネットの情報（VPC ID・サブネットID・RDS用セキュリティグループID）を入力として受け取る。アプリケーション層（`envs/verify`）は、DB層が出力する接続情報（`db_url_secret_arn`・エンドポイント等）を参照する。この受け渡し方法（`terraform_remote_state`によるstate間の直接参照か、Secrets Manager側のシークレット名をタグ・命名規則で検索する疎結合な参照か）は、実装フェーズで確定する。
- README §10の運用ルールを変更し、通常の`terraform destroy`（コスト管理目的、ECS Fargate等の常時課金リソースを止める）はアプリケーション層のstateに対してのみ実行し、DB層のstateは対象外とする。DB自体を破棄したい場合（検証プロジェクト完全終了時等）は、DB層のディレクトリで明示的に`terraform destroy`を実行する、別の操作として扱う。
- `deletion_protection`・`skip_final_snapshot`等のRDSパラメータ（現行は都度破棄前提でいずれも無効化）は、永続化する運用に合わせて実装フェーズで見直す（例えば`deletion_protection = true`への変更、誤destroy防止のための`lifecycle { prevent_destroy = true }`併用等）。

## 検討した代替案

- **案2（単一state + prevent_destroy/target運用）**: state分割を避けられる分シンプルだが、`terraform destroy`をtarget指定なしで実行した場合に`prevent_destroy`はエラーで停止するだけであり、「アプリ層だけを安全に、日常的に」destroyする運用には向かない。誤ってtarget指定を外した際の失敗コストや、state肥大化に伴うplan/apply時間の増加も避けられないため、恒常的な運用としては不採用とした。
- **案3（現状維持）**: 追加の構成変更が不要な点はシンプルだが、コンテキストで述べた再計算コスト（時間・Bedrock費用）と、DB層への誤操作リスクを解消できないため、要件定義書14章Open Issue #7（予算・コスト方針）で未解決だった論点を踏まえ、不採用とした。

## 結果・影響

- Terraformのディレクトリ構成が、`envs/verify`単独から、ネットワーク（ADR-0036、外部参照のみで新規stateは不要な想定）・DB層・アプリケーション層の複数root構成に変わる。`deploy.bat`/`destroy.bat`・`scripts/deploy.ps1`/`destroy.ps1`（README記載の一括実行スクリプト）は、複数ディレクトリに対する`apply`/`destroy`の実行順序（DB層 → アプリケーション層の順でapply、destroyはアプリケーション層のみ）を制御するよう改修が必要になる。この改修自体は実装フェーズで行う。
- `docs/requirement/202608100910_MCPサーバークライアントAWSデプロイ要件定義書.md`の14章Open Issue #7（予算・コスト方針）は、本ADRにより「RDSは通常のdestroy運用の対象外とし、ECS Fargate等のみを都度停止する」という方針で一部解消されるが、DB層自体のコスト（RDSの常時起動コスト）を許容するか、あるいはDB層も含めた完全停止を別途どのタイミングで行うかは、引き続き発注者確認が必要な論点として残る。同要件定義書12章の受け入れ基準（「検証終了後、terraform destroy等でAWSリソース（RDSを含む）を破棄できることを確認する」）も、本ADRの内容に合わせて見直しが必要になる。
- ADR-0026（DB配置方針）・ADR-0027（S3バックエンド採用）自体の決定内容（RDSを採用すること、S3バックエンドを使うこと）に変更はないが、両ADRが前提としていた「単一state・単一環境」という暗黙の運用は本ADRにより更新される。両ADRには本ADRへの参照を追記する。
- state分割により、ネットワーク・DB・アプリケーションの3層それぞれで異なるチーム・担当者がapply権限を持つ運用（IAMポリシーによるstate単位でのアクセス制御）も将来的に可能になる。
