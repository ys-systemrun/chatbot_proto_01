# terraform/main/app — app 構成（ECS 常駐サービス周辺）

アプリ側の ECS 常駐サービス周辺をまとめた root 構成（ADR-0039）。database 構成の出力（サブネット・SG・DB 接続シークレット ARN 等）を `terraform_remote_state` で参照するため、database 構成を先に apply しておく。
集約サービス（tag_selector_mcp / knowledge_mcp / agent_invitro / admin_ui を1タスク・4コンテナ, ADR-0095）の起動数 `app_desired_count` がシード完了ゲートになる。
`apply-app.bat` / `apply-all.bat` で apply、`destroy-app.bat` / `destroy-all.bat` で破棄する（RDS は残る）。

## 構成

| 名前 | 説明 |
|---|---|
| [`backend.tf`](backend.tf) | terraform / provider（aws・random）設定と S3 バックエンド宣言（bucket / key / region は `-backend-config` で注入。key は `STATE_KEY_APP`） |
| [`variables.tf`](variables.tf) | 構成の変数（リージョン・アカウントID・`name_prefix`・remote state 参照先・イメージタグ・Bedrock モデル・タスクサイズ・`app_desired_count`・admin_ui 許可 CIDR・予算アラート等）。値は `.env` の `TF_VAR_*` と deploy の `-var` から供給 |
| [`main.tf`](main.tf) | database 構成の remote state 参照と、`modules/ecr`（アプリ用 5 リポジトリ）・`modules/ecs-cluster`・`modules/mcp-inspector-task`・`modules/admin-ui-alb`・`modules/ecs-app-task`（集約サービス）・`modules/cost-alert`（メール指定時のみ）の呼び出し |
| [`outputs.tf`](outputs.tf) | ECR URL・クラスタ名・集約サービス名・MCP Inspector タスク family・予算名・admin_ui ALB の DNS 名（deploy の push / 安定待機 / import-data が参照） |
| [`.terraform.lock.hcl`](.terraform.lock.hcl) | プロバイダのバージョン・ハッシュのロックファイル |
