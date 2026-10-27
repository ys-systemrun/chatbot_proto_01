# terraform/modules/mcp-inspector-task — MCP Inspector 検証タスク定義

MCP Inspector（Node.js CLI）を入れた検証専用イメージのタスク定義だけを作るモジュール（ADR-0029）。
常駐サービスは作らず、Phase 6 の検証で `aws ecs run-task` + ECS Exec により起動して集約タスクの MCP サーバーへ `tools/list` / `tools/call` を行う。
`terraform/main/app` から呼ばれる。

## 構成

| 名前 | 説明 |
|---|---|
| [`main.tf`](main.tf) | 変数（family・リージョン・イメージ・CPU/メモリ・ログ保持日数）、実行ロール・タスクロール（ECS Exec 用）、ロググループ、Fargate タスク定義、出力 `task_definition_arn` / `family` |
