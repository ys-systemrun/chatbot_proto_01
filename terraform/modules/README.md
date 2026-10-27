# terraform/modules — Terraform 再利用モジュール

`terraform/main/` の root 構成（database / app）から呼び出すモジュール群。各モジュールはリソース定義だけを持ち、state や backend は持たない。
どの構成から呼ばれるかは ADR-0039 の 2 層分割に従う（database 構成: network / database / ecr / db-init-task、app 構成: ecr / ecs-cluster / ecs-app-task / admin-ui-alb / mcp-inspector-task / cost-alert）。

## 構成

| 名前 | 説明 |
|---|---|
| [`network/`](network/README.md) | 既存 VPC/サブネットを data 参照し、集約タスク・RDS・検証タスク・ALB 用の SG と、タスク用サブネットの IGW 経路照合を行う（ADR-0036 / ADR-0104）。database 構成から呼ばれる |
| [`database/`](database/README.md) | RDS PostgreSQL(pgvector) と、`DATABASE_URL` 等の接続文字列・ロール用パスワードの Secrets Manager シークレット。database 構成から呼ばれる |
| [`ecr/`](ecr/README.md) | 名前リストで ECR リポジトリを作る（push 時スキャン有効）。database 構成（db-init）と app 構成（5 件）から呼ばれる |
| [`db-init-task/`](db-init-task/README.md) | db_init（シード・マイグレーション・import・query・export）の run-task 用タスク定義と IAM・ロググループ。database 構成から呼ばれる |
| [`ecs-cluster/`](ecs-cluster/README.md) | ECS Fargate クラスタ（Container Insights 有効）。app 構成から呼ばれる |
| [`ecs-app-task/`](ecs-app-task/README.md) | 常駐4サービスを1タスク・4コンテナで動かす ECS サービス・タスク定義・IAM（ADR-0095）。app 構成から呼ばれる |
| [`admin-ui-alb/`](admin-ui-alb/README.md) | admin_ui 用の internet-facing ALB・ターゲットグループ・HTTP リスナー・社内 CIDR 許可ルール（ADR-0041）。app 構成から呼ばれる |
| [`mcp-inspector-task/`](mcp-inspector-task/README.md) | MCP Inspector 検証用イメージのタスク定義のみ（ADR-0029）。app 構成から呼ばれる |
| [`cost-alert/`](cost-alert/README.md) | Amazon Bedrock の月額予算アラート（AWS Budgets + メール通知）。app 構成から、通知先メール指定時のみ呼ばれる |
