# terraform/modules/database — RDS(pgvector) と接続シークレット

Amazon RDS for PostgreSQL（pgvector 拡張）を検証用の最小構成で作るモジュール（ADR-0026 / ADR-0037）。
アプリは `DATABASE_URL` を1本の接続文字列で要求するため、`random_password` から完全な接続 URL を組み立てた独自の Secrets Manager シークレットを作り、ECS タスク定義へ secrets 注入させる。
`terraform/main/database` から呼ばれる（root 構成の `main/database` とは別物。「db モジュール」と呼び分ける, ADR-0039 §10）。

## 構成

| 名前 | 説明 |
|---|---|
| [`main.tf`](main.tf) | 変数・DB サブネットグループ・パラメータグループ・RDS インスタンス（削除保護・最終スナップショット設定）と、knowledge / conversation の接続 URL シークレット、export_reader・migrator・app 各ロールのパスワード／接続 URL シークレット（ロール作成は db_init が SQL で行う）および出力をすべて定義 |
