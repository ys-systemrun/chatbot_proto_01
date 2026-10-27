# data/ — 評価用クエリと元データの作業場所

リポジトリ直下の作業用データ置き場です。git で管理しているのは評価用クエリ CSV・カテゴリ CSV・縮小版データと、元データを加工した Go スクリプトです。
`docker compose` では `web_backend` の `/data` にマウントされ、MRR 評価（`src/main/evaluate.py`）がここの評価用 CSV を読みます。
**db_init のシード元データはここではなく [`db_init/data/`](../db_init/data/README.md)（DVC 管理, ADR-0097 / ADR-0098）** です。
QA 本体などのフルデータ（下表の「未追跡」）は git に入れない方針のため、ローカルにある作業用コピーです。

## 構成

| 名前 | 説明 |
|---|---|
| [`eval_queries.csv`](eval_queries.csv) | 評価用クエリ（`query,qa_id`）。手作りの質問と正解 QA の GUID。MRR 評価（`EVAL_QUERIES_CSV`）と評価ランナーのゴールデンセット作成（handpicked, `evals/runner/golden.py`）で使う |
| [`eval_noise_queries.csv`](eval_noise_queries.csv) | 範囲外の質問（`query`）。回答を控えるのが正解の質問として、ゴールデンセット作成（out_of_scope）で使う |
| [`category.csv`](category.csv) | 広場 QA のカテゴリ一覧（`id,name`、8件） |
| [`exportjson_withguid_small.json`](exportjson_withguid_small.json) | 広場 QA 本体の縮小版（約200件）。`title`・`category`・`question`・`answer`・`guid` の配列 |
| [`question_altered_small.csv`](question_altered_small.csv) | 言い換え質問文の縮小版（`qa_id,text`） |
| [`main.go`](main.go) | QA JSON と言い換え CSV の加工ツール（Go）。GUID 付与、GUID の欠落・不連続・重複の検査、GUID 順のソート・分割・結合、JSON と CSV のマージ（`merged_output.csv` の生成）などの関数を持ち、`main()` で使うものを切り替える |
| [`go.mod`](go.mod) / [`go.sum`](go.sum) | `main.go` の Go モジュール定義（依存: `github.com/google/uuid`）。devcontainer の `postCreate.sh` が `go mod tidy` する |
| [`exportjson.json`](exportjson.json) | （未追跡）広場 QA のエクスポート元データ。`{"posts": [{title, category, question, answer}, ...]}` 形式 |
| [`exportjson_toalter.json`](exportjson_toalter.json) | （未追跡）`exportjson.json` と同一内容のコピー（言い換え質問文の作成用） |
| [`exportjson_withguid.json`](exportjson_withguid.json) | （未追跡）`exportjson.json` の各レコードに `guid` を付けた配列。同名のファイルが `db_init/data/hiroba_qa/` にシード元データとして置かれている |
| [`question_altered.csv`](question_altered.csv) | （未追跡）言い換え質問文のフル版（`qa_id,text`、約5,000行） |
| [`merged_output.csv`](merged_output.csv) | （未追跡）`main.go` で QA JSON と言い換え CSV を GUID で結合した確認用 CSV（`guid,category,title,original_q,original_a,altered_a`、Shift_JIS） |
| [`tags.csv`](tags.csv) | （未追跡）タグ一括インポート用 CSV のサンプル（`name,parent_name,description`。管理画面のタグインポートが受け付ける形式） |
| [`trouble_shooting.html`](trouble_shooting.html) | （未追跡）維津美V7 システムのトラブルシューティング文書（HTML）。同名のファイルが `db_init/data/troubleshooting/` にシード元データとして置かれている |
| [`trouble_shooting_netauth.html`](trouble_shooting_netauth.html) | （未追跡）ネット認証のトラブルシューティング文書（HTML）。同上 |

`original_qa_frac/`（QA を GUID ごとのディレクトリに分けた作業用データ）は Git 管理外（`.gitignore`）です。
