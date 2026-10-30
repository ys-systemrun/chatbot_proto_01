# evals/queries — 手作りの評価用クエリ

ゴールデンセットの元にした、手作りの質問です（旧 `data/` から移設）。

| 名前 | 説明 |
|---|---|
| [`eval_queries.csv`](eval_queries.csv) | 評価用クエリ（`query,qa_id`）。手作りの質問と正解 QA の GUID。ゴールデンセット作成（handpicked, `runner/golden.py`）と、`web_backend` の旧 MRR 評価（`src/main/evaluate.py`, `EVAL_QUERIES_CSV`）で使う |
| [`eval_noise_queries.csv`](eval_noise_queries.csv) | 範囲外の質問（`query`）。回答を控えるのが正解の質問として、ゴールデンセット作成（out_of_scope）と旧 MRR 評価（`EVAL_NOISE_QUERIES_CSV`）で使う |

`docker-compose.yml` で `web_backend` の `/data` にマウントされます。
