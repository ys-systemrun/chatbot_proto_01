# evals/tests — 評価ランナーのテスト

`evals/runner/` を pytest で検証します（`evals/` で `python -m pytest tests`）。AWS・Bedrock・claude CLI には触れず、
admin_ui への問い合わせや `subprocess.run` は差し替えます。

## 構成

| 名前 | 説明 |
|---|---|
| [`test_feedback.py`](test_feedback.py) | `pull-feedback` の変換（会話 → 1行1件の JSON）と増分取り込み |
| [`test_run.py`](test_run.py) | ゴールデンセットの作成・評価の実行・採点・比較（一時ディレクトリに最小のシード元データを作って実行） |
| [`test_judge_backend.py`](test_judge_backend.py) | 採点方式 `claude-code`（ADR-0101）: `claude -p` の呼び出し方、API 課金への切り替わり防止、使用量の上限での中断と再開、再採点 |
| [`test_repeat.py`](test_repeat.py) | 繰り返し実行の集計（平均・ばらつき）と、揺れを考慮した比較の判定 |
