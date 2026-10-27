# terraform/bootstrap — Terraform state 用 S3 バケット（Phase 0）

database / app / datastore 構成の Terraform state を保管する S3 バケットを、それらの構成とは別に作る独立した root 構成（ADR-0027 / ADR-0039）。
このバケットを作ること自体が目的のため、bootstrap 自身の state は S3 ではなくローカルに置く（循環依存の回避）。
通常は `terraform/bootstrap.bat`（`deploy bootstrap`）から実行し、バケット名は `.env` の `STATE_BUCKET` を使う。

## 構成

| 名前 | 説明 |
|---|---|
| [`main.tf`](main.tf) | provider・変数（`aws_region` / `state_bucket_name` / `create_lock_table`）と、state バケット（バージョニング・暗号化・パブリックアクセスブロック、account-regional 名前空間）および任意の DynamoDB ロックテーブル（Terraform 1.10 未満向け）を定義。出力は `state_bucket_name` / `lock_table_name` |
| [`.terraform.lock.hcl`](.terraform.lock.hcl) | プロバイダのバージョン・ハッシュのロックファイル（`terraform init` が生成。コンテナ内 linux_amd64 実行に対応させておく） |

> Git 管理外: `.terraform/`（プロバイダ等の作業ディレクトリ）と `terraform.tfstate`（bootstrap のローカル state）。
