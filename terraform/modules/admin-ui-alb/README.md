# terraform/modules/admin-ui-alb — admin_ui 用 ALB

admin_ui（QA・タグ管理 UI）を社内ネットワークのブラウザから開くための internet-facing ALB を作るモジュール（ADR-0041）。
HTTP(80) リスナーのみ（HTTPS は証明書発行後に追加予定）。ALB の SG 本体は `modules/network` が作り、ここでは許可 CIDR からの 80 番インバウンドルールだけを追加する。
`terraform/main/app` から呼ばれ、ターゲットグループ ARN を `modules/ecs-app-task` に渡す。

## 構成

| 名前 | 説明 |
|---|---|
| [`variables.tf`](variables.tf) | 入力変数（`name_prefix`・VPC・パブリックサブネット・ALB SG・コンテナポート・許可 CIDR・ヘルスチェックパス・アイドルタイムアウト） |
| [`main.tf`](main.tf) | ALB・ターゲットグループ（`target_type=ip`）・HTTP リスナー・許可 CIDR のインバウンドルール |
| [`outputs.tf`](outputs.tf) | `target_group_arn`（ecs-app-task へ）・`dns_name`（アクセス先）・`alb_arn`・`listener_arn` |
