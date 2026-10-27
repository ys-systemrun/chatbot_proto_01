# .dvc/ — DVC の設定

データ本体を git ではなく S3 の DVC リモートで管理するための DVC 設定です（ADR-0097）。
対象は `db_init/data/` のシード元データと `evals/` の評価結果（`runs/`・`feedback/`, ADR-0099）。
操作は `terraform\dvc.bat`（`pull` / `add` / `push`）から行います。手順は `terraform/README.md` の「Phase 0.5」を参照してください。

## 構成

| 名前 | 説明 |
|---|---|
| [`config`](config) | DVC の共有設定。既定リモート `storage`（S3 バケット）と、利用統計の送信停止（`analytics = false`） |
| [`.gitignore`](.gitignore) | DVC のローカル専用ファイル（`config.local`・`tmp/`・`cache/`）を git の対象外にする |
