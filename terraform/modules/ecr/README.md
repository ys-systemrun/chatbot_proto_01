# terraform/modules/ecr — ECR リポジトリ

渡された名前リストの数だけ ECR リポジトリを作るモジュール（push 時の脆弱性スキャン有効, ADR-0030）。
`terraform/main/database`（`db-init` 1 件）と `terraform/main/app`（knowledge-mcp / tag-selector-mcp / agent-invitro / mcp-inspector / admin-ui の 5 件）から分割して呼ばれる。

## 構成

| 名前 | 説明 |
|---|---|
| [`main.tf`](main.tf) | 変数（`repository_names` / `image_tag_mutability`）、`aws_ecr_repository`（for_each）、出力 `repository_urls` / `repository_arns`（名前→URL/ARN のマップ） |
