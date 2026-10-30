# db_init/data — シード元データ

db_init イメージに `/data` として同梱されるシード元データです（ADR-0034）。
情報源ごとにディレクトリを分け（ADR-0098）、データ本体は git ではなく DVC で管理します（ADR-0097）。
git に入っているのは、このファイルと情報源ごとの `.dvc`（内容ハッシュ）だけです。

| ディレクトリ | `.dvc` | 内容 | 投入先テーブル |
|---|---|---|---|
| `hiroba_qa/` | `hiroba_qa.dvc` | 維津美の広場 QA。`category.csv`（カテゴリ）、`hiroba_qa_original.csv`（QA 本体。各行に uuid、カテゴリは ID, ADR-0108）、`question_altered.csv`（言い換え質問文） | `hiroba_category` / `hiroba_qa_original` / `hiroba_question_altered` |
| `troubleshooting/` | `troubleshooting.dvc` | トラブルシューティング記事の CSV（`trouble_shooting.csv` / `trouble_shooting_netauth.csv`, 1 行 = 1 記事）。元の HTML を `<h2>` 単位で記事化（ADR-0076）したものを [`../tools/troubleshooting_html_to_csv.py`](../tools/troubleshooting_html_to_csv.py) で変換。`uuid` と元の表を含む `body_html` を持つ（ADR-0108） | `troubleshooting_article`（`source_key` はファイル名と同じ） |
| `redmine_error_taiou/` | `redmine_error_taiou.dvc` | Redmine Wiki のエラー対応ページを整形した CSV（`redmine_error_taiou.csv`, 1 行 = 1 記事, 各行に `uuid`）。顧客名は伏せ字済み。変換は [`../tools/redmine_wiki_to_csv.py`](../tools/redmine_wiki_to_csv.py)（ADR-0105） | `troubleshooting_article`（`source_key=redmine_error_taiou`） |

どのファイルを読むかは環境変数で指定します（`/data` からの相対パス）:
`QA_ORIGINAL_FILE` / `QUESTION_ALTERED_FILE` / `CATEGORY_FILE`（ローカルは `.env`、AWS は `terraform/.env` の `TF_VAR_*`）。
トラブルシューティング記事（CSV）のパスは `db_init/src/main.py` の `TROUBLESHOOTING_SOURCES` に固定です。

シード元データは CSV に統一していく方針です（ADR-0108）。新しく CSV を作る・書き出すときは ADR-0108 の書式
（UTF-8・BOM なし・LF・全フィールド引用符、列名は投入先テーブルの列名、識別子を先頭列に必須）に従ってください。

`error_taiou_o/` を置いた場合、それは CSV に変換する前の Redmine Wiki の保存 HTML（顧客名を含む）です。
git（`.gitignore`）にもイメージ（`../.dockerignore`）にも入りません。

## 操作（リポジトリルートで実行）

```
terraform\dvc.bat pull                          データを取得
terraform\dvc.bat add db_init/data/hiroba_qa    変更を記録（.dvc が更新される → git commit）
terraform\dvc.bat push                          DVC リモートへ送る（忘れると他の人・デプロイが取得できない）
```

詳細は `terraform/README.md` の「Phase 0.5: ナレッジデータ（DVC）」を参照してください。

## 構成

| 名前 | 説明 |
|---|---|
| [`hiroba_qa.dvc`](hiroba_qa.dvc) | `hiroba_qa/` の DVC ポインタ（内容ハッシュ・ファイル数）。`dvc pull` で `hiroba_qa/` が展開される |
| [`troubleshooting.dvc`](troubleshooting.dvc) | `troubleshooting/` の DVC ポインタ |
| [`redmine_error_taiou.dvc`](redmine_error_taiou.dvc) | `redmine_error_taiou/` の DVC ポインタ |
| [`.gitignore`](.gitignore) | DVC が展開するデータ本体（`/hiroba_qa`・`/troubleshooting`・`/redmine_error_taiou`）を git の対象外にする（`dvc add` が生成）。加工前の `/error_taiou_o` も対象外にする |
