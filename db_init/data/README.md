# db_init/data — シード元データ

db_init イメージに `/data` として同梱されるシード元データです（ADR-0034）。
情報源ごとにディレクトリを分け（ADR-0098）、データ本体は git ではなく DVC で管理します（ADR-0097）。
git に入っているのは、このファイルと情報源ごとの `.dvc`（内容ハッシュ）だけです。

| ディレクトリ | `.dvc` | 内容 | 投入先テーブル |
|---|---|---|---|
| `hiroba_qa/` | `hiroba_qa.dvc` | 維津美の広場 QA。`category.csv`（カテゴリ）、`exportjson_withguid.json`（QA 本体, GUID 付与済み）、`question_altered.csv`（言い換え質問文） | `hiroba_category` / `hiroba_qa_original` / `hiroba_question_altered` |
| `hiroba_qa/small/` | （`hiroba_qa.dvc` に含む） | 開発・検証用の縮小版（QA 本体・言い換えのみ。カテゴリはフル版と共通） | 同上 |
| `troubleshooting/` | `troubleshooting.dvc` | トラブルシューティング記事の HTML（`trouble_shooting.html` / `trouble_shooting_netauth.html`）。`<h2>` 単位で記事化（ADR-0076） | `troubleshooting_article` |

どのファイルを読むかは環境変数で指定します（`/data` からの相対パス）:
`QA_ORIGINAL_FILE` / `QUESTION_ALTERED_FILE` / `CATEGORY_FILE`（ローカルは `.env`、AWS は `terraform/.env` の `TF_VAR_*`）。
トラブルシューティング HTML のパスは `db_init/src/main.py` の `TROUBLESHOOTING_SOURCES` に固定です。

## 操作（リポジトリルートで実行）

```
terraform\dvc.bat pull                          データを取得
terraform\dvc.bat add db_init/data/hiroba_qa    変更を記録（.dvc が更新される → git commit）
terraform\dvc.bat push                          DVC リモートへ送る（忘れると他の人・デプロイが取得できない）
```

詳細は `terraform/README.md` の「Phase 0.5: ナレッジデータ（DVC）」を参照してください。
