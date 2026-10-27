# terraform/modules/network — 既存 VPC 参照と SG

既存 VPC・サブネットを data source で参照し（新規作成しない, ADR-0036）、本システム用のセキュリティグループだけを作るモジュール。
ADR-0104 により VPC エンドポイントは使わず、ECS タスク・run-task を置くサブネットに `0.0.0.0/0 → インターネットゲートウェイ` の経路があるかを plan 時に照合する（無ければ precondition / postcondition で停止）。
`terraform/main/database` から呼ばれる。

## 構成

| 名前 | 説明 |
|---|---|
| [`variables.tf`](variables.tf) | 入力変数（`name_prefix`・`vpc_id`・`private_subnet_ids`・`workload_subnet_id`・`public_subnet_ids`・各サービスのポート） |
| [`main.tf`](main.tf) | VPC 参照、SG（集約タスク・RDS・検証タスク・admin_ui ALB）と許可ルール（ALB→admin_ui、検証タスク→MCP、タスク→RDS 等）、タスク用サブネットの決定とルートテーブルの IGW 経路照合 |
| [`outputs.tf`](outputs.tf) | VPC ID・サブネット ID 群（`workload_subnet_ids` 含む）・各 SG ID を出力（database 構成の outputs 経由で app 構成へ渡る） |
