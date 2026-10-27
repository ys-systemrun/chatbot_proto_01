# terraform/main — Terraform の root 構成（state 単位）

state を分けた 3 つの Terraform root 構成を置く。database 構成と app 構成は ADR-0039 の 2 層分割（依存は database ← app の一方向）、datastore 構成は ADR-0097 で追加した破棄しない長寿命の層。
いずれも `terraform/deploy`（`apply-*.bat` / `destroy-*.bat`）が `-backend-config` で S3 バックエンドを注入して `init` / `apply` する。

## 構成

| 名前 | 説明 |
|---|---|
| [`datastore/`](datastore/README.md) | ナレッジデータの DVC リモート用 S3 バケットだけを持つ構成（ADR-0097）。`apply-datastore.bat` / `apply-all.bat` から apply。破棄コマンドは無い |
| [`database/`](database/README.md) | ネットワーク（SG・経路照合）+ RDS(pgvector) + シード用 ECR / db_init タスク定義 + import 用 S3 バケット。`apply-database.bat` で apply、`destroy-database.bat` で破棄 |
| [`app/`](app/README.md) | ECS クラスタ + 集約サービス（4コンテナ1タスク）+ admin_ui 用 ALB + MCP Inspector タスク定義 + 予算アラート + アプリ用 ECR。`apply-app.bat` で apply、`destroy-app.bat` で破棄 |
