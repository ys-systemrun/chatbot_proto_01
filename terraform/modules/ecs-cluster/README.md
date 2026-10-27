# terraform/modules/ecs-cluster — ECS Fargate クラスタ

ECS Fargate クラスタを作るモジュール（ADR-0024）。Container Insights を既定で有効にする。
`terraform/main/app` から呼ばれ、集約サービスと各 run-task（seed / migrate / query / import-data / MCP Inspector）が使う。

## 構成

| 名前 | 説明 |
|---|---|
| [`main.tf`](main.tf) | 変数（`cluster_name` / `enable_container_insights`）、`aws_ecs_cluster` と Fargate キャパシティプロバイダ設定、出力 `cluster_arn` / `cluster_name` |
