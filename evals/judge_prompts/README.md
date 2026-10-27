# evals/judge_prompts — LLM 採点のプロンプト

評価ランナーの LLM 採点（`runner/judge.py`）が使うプロンプトです。プロンプトのハッシュは実行結果の `meta.json` と
`history.csv` に記録されるため、書き換えると以前の実行と採点条件が変わります（比較するときは `judge` で再採点する）。

## 構成

| 名前 | 説明 |
|---|---|
| [`answer.md`](answer.md) | 回答の採点プロンプト。質問・模範解答・検索結果・回答を受け取り、correctness（1〜5）・faithfulness（1〜5）・declined と理由を JSON で返すよう指示する |
