# terraform/main/datastore — datastore 構成（DVC リモート用 S3）

ナレッジデータ（シード元データ）の DVC リモートとなる S3 バケットだけを持つ root 構成（ADR-0097）。
database / app とは独立した長寿命の層で、`destroy-app` / `destroy-database` の対象外（破棄コマンドも用意しない）。
`apply-datastore.bat`（`deploy apply-datastore`）または `apply-all.bat` の先頭で冪等に apply される。

## 構成

| 名前 | 説明 |
|---|---|
| [`backend.tf`](backend.tf) | terraform / provider 設定と S3 バックエンド宣言（bucket / key / region は `-backend-config` で注入。key は `.env` の `STATE_KEY_DATASTORE`） |
| [`main.tf`](main.tf) | 変数（`aws_region` / `name_prefix`）、DVC 用 S3 バケット（バージョニング・暗号化・パブリックアクセスブロック・`prevent_destroy`）、出力 `dvc_bucket_name` / `dvc_remote_url`（`.dvc/config` の remote URL と一致させる） |
| [`.terraform.lock.hcl`](.terraform.lock.hcl) | プロバイダのバージョン・ハッシュのロックファイル |
