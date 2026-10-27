# terraform/main/database — database 構成（ネットワーク + RDS + シード周辺）

ネットワーク基盤（既存 VPC 参照 + SG + タスク用サブネットの経路照合）、RDS PostgreSQL(pgvector) と接続シークレット、シード用 ECR と db_init タスク定義、全データインポート用 S3 バケットをまとめた root 構成（ADR-0039。旧 verify-network / verify-database / verify の db_init 部分を統合）。
RDS は永続化（`deletion_protection=true`）し、通常の `destroy-app` の対象外。出力は app 構成が `terraform_remote_state` で参照する。
`apply-database.bat` / `apply-all.bat` で apply、`destroy-database.bat` / `destroy-all.bat` で破棄する。

## 構成

| 名前 | 説明 |
|---|---|
| [`backend.tf`](backend.tf) | terraform / provider（aws・random）設定と S3 バックエンド宣言（bucket / key / region は `-backend-config` で注入。key は `STATE_KEY_DATABASE`） |
| [`variables.tf`](variables.tf) | 構成の変数（リージョン・`name_prefix`・既存 VPC/サブネット ID・RDS 設定・シードデータのパス・Bedrock モデル ID 等）。値は `.env` の `TF_VAR_*` から供給 |
| [`main.tf`](main.tf) | `modules/network`・`modules/database`・`modules/ecr`（db-init 1件）・`modules/db-init-task` の呼び出し、旧 VPC エンドポイントを state から外す `removed` ブロック（ADR-0104）、import 用 S3 バケット（ADR-0066） |
| [`outputs.tf`](outputs.tf) | app 構成・deploy が参照する出力（サブネット・各 SG・DB 接続シークレット ARN・RDS エンドポイント・`db_init_task_family`・`import_bucket_name`・ECR URL 等） |
| [`.terraform.lock.hcl`](.terraform.lock.hcl) | プロバイダのバージョン・ハッシュのロックファイル |

> `modules/database`（RDS のモジュール）とこの `main/database`（root 構成）は別物。「db モジュール」「database 構成」と呼び分ける（ADR-0039 §10）。
