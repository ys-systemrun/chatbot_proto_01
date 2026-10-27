# evals/runner — 評価ランナー本体

`evals\eval.bat` から `python -m runner <コマンド>` として実行される評価ランナーです（ADR-0099 §5）。
コマンドの使い方・出力の形式は [`evals/README.md`](../README.md) を参照してください。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ定義（docstring のみ） |
| [`__main__.py`](__main__.py) | CLI。`pull-feedback` / `build-golden` / `run`（`--repeat`）/ `compare` / `judge` の引数を解釈して各モジュールを呼ぶ |
| [`client.py`](client.py) | admin_ui（AWS 検証環境）への問い合わせ（リリース情報の取得・質問の送信）。標準ライブラリのみ |
| [`feedback.py`](feedback.py) | `pull-feedback`。admin_ui の `/api/evaluated_messages` から 👍/👎 の付いた回答を取得し、増分だけを `evals/feedback/<日時>.jsonl` に追記する |
| [`golden.py`](golden.py) | ゴールデンセット（`evals/golden/<名前>.csv`）の読み込みと初版の作成（`build-golden`）。模範解答はシード元データ `db_init/data/hiroba_qa/` から引く |
| [`run.py`](run.py) | `run` / `compare` / `judge`。ゴールデンセットを方式（pipeline / agentic）ごとに送って採点し、`evals/runs/<日時>_<セット>_<方式>/` と `history.csv` に保存する |
| [`judge.py`](judge.py) | LLM 採点（Claude Opus）。採点プロンプト `judge_prompts/answer.md` を使い、Bedrock と Claude Code（`claude -p`）の2方式を切り替える（ADR-0101）。トークン数と概算費用も記録する（ADR-0100） |
| [`scoring.py`](scoring.py) | 決定的な採点（出典の順位・回答を控えたかの判定）、集計、実行どうしの比較 |
| [`repeat.py`](repeat.py) | `run --repeat N` の繰り返し実行のグループ化と、揺れ（標準誤差）を考慮した比較。集計を `evals/runs/groups/<グループ ID>.md` に書く |
