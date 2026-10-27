# terraform/modules/db-init-task — db_init の run-task 用タスク定義

db_init コンテナの ECS タスク定義だけを作るモジュール（常駐サービスは作らない, ADR-0030）。
`terraform/deploy` が `run-task` で都度起動し、environment の上書きでシード・マイグレーション（`MIGRATE_ONLY`）・全データインポート（`IMPORT_MODE`）・アドホック SQL（`QUERY_MODE`）・退避（`EXPORT_MODE`）を切り替える。
`terraform/main/database` から呼ばれる。

## 構成

| 名前 | 説明 |
|---|---|
| [`main.tf`](main.tf) | 変数（family・イメージ・CPU/メモリ・environment・secrets・Bedrock / import 用 S3 の有効化等）、実行ロール（secrets 取得）・タスクロール（ECS Exec・Bedrock・import バケット読み書き）、ロググループ `/ecs/db-init`、Fargate タスク定義、出力 `task_definition_arn` / `family` |
