# evals/ — 評価ランナーと評価結果

回答品質の改善ループ（ADR-0099）で使う評価ランナーと、その結果を置くディレクトリです。
結果はリポジトリに残し、Claude Code に読ませて原因分析・修正案作成に使います。

```
evals/
  eval.bat            評価ランナーの呼び出し口（chatbot-evals イメージで python -m runner を実行）
  Dockerfile          評価ランナーのイメージ（python + Anthropic SDK）。eval.bat が毎回 build（キャッシュで即時）
  .env.example        設定の雛形 → evals/.env にコピーして記入（Git 管理外）
  runner/             評価ランナー本体
  judge_prompts/      LLM 採点のプロンプト（answer.md）
  golden/             ゴールデンセット（<名前>.csv）
  history.csv         実行ごとの数値と版の推移（git 管理。質問・回答の文は含めない）
  runs/               ゴールデンセット評価の結果（<日時>_<セット>_<方式>/）… DVC 管理（runs.dvc）
  feedback/           人手評価の取り込み結果（<日時>.jsonl）… DVC 管理（feedback.dvc）
  tests/              ランナーのテスト（python -m pytest tests）
```

## 評価データの管理（git ではなく DVC）

`runs/` と `feedback/` には利用者の質問・回答・回答時の参考情報（ナレッジ本文）が入るため、git には入れず
DVC で管理します（ADR-0099 §5。ナレッジ本体を git に入れない ADR-0097 と同じ方針）。git に入るのは
`feedback.dvc`・`runs.dvc`（ポインタ）と `history.csv`（数値だけ）です。

```
（評価や取り込みの後）
terraform\dvc.bat add evals/feedback evals/runs
git add evals/feedback.dvc evals/runs.dvc evals/history.csv
git commit -m "evals: <内容>"
terraform\dvc.bat push

（別のマシンで評価データを取得するとき）
terraform\dvc.bat pull
```

## 準備

1. `evals/.env.example` を `evals/.env` にコピーし、`EVAL_BASE_URL` に admin_ui の URL を書く。
   URL は `apply-app` の完了時に表示される `admin_ui_alb_dns_name` に `http://` を付けたもの。
2. Docker Desktop を起動しておく。admin_ui の ALB は社内ネットワークからのみ到達できる。
3. LLM 採点（`run`）は `terraform/.env` の AWS 認証情報で Amazon Bedrock を呼ぶ（deploy と同じ）。
4. 採点の模範解答はシード元データから引くため、`terraform\dvc.bat pull` 済みであること（ADR-0097）。

## コマンド

| コマンド | 内容 |
|---|---|
| `evals\eval.bat pull-feedback` | チャット画面で付けた 👍/👎・理由・リリースの増分を `evals/feedback/<日時>.jsonl` に保存する |
| `evals\eval.bat build-golden` | 初版のゴールデンセット `evals/golden/v1.csv` を作る（最初の1回だけ。既にあれば `--force` が必要） |
| `evals\eval.bat run` | ゴールデンセット v1 を両方式（pipeline / agentic）で送り、採点して `evals/runs/` に保存する |
| `evals\eval.bat run --mode agentic --limit 5` | 1方式・先頭5問だけ試す（`--no-judge` で LLM 採点なし） |
| `evals\eval.bat compare <実行A> <実行B>` | 2回の実行結果を質問単位で比較する（`evals/runs/` のディレクトリ名） |

`snapshot`（ナレッジのスナップショット）は段階④で追加します。

## ゴールデンセット（golden/<名前>.csv）

| 列 | 内容 |
|---|---|
| `id` | 質問の ID。実行結果どうしの比較キーなので、一度決めたら変えない |
| `question` | 質問文 |
| `expected_source_ids` | 正解の出典（`qa:<guid>` / `troubleshooting:<id>`、空白区切りで複数可）。空なら出典は採点しない |
| `expected_answer_points` | 回答に含むべき要点（任意）。空なら正解 QA の回答文を模範解答にする |
| `category` | `handpicked`（手作り）/ `paraphrase_indexed`（言い換え質問文から抽出）/ `out_of_scope`（範囲外）/ `feedback`（人手評価から追加）など |
| `should_answer` | `true`=回答すべき / `false`=範囲外で回答を控えるのが正解 |
| `note` | 補足 |

- 初版（v1, 27問）は `data/eval_queries.csv`（4問）・`data/eval_noise_queries.csv`（3問）と、言い換え質問文から seed 固定で抽出した20問。
- **`paraphrase_indexed` の質問は検索用に埋め込み済みの文そのもの**なので、出典の一致率は実際より高く出る。
  回答の質の比較には使えるが、検索の評価は `handpicked` と `feedback` を重視する。
- 人手評価で 👎 になった質問は、内容を確認してから `category=feedback` で追記していく（回帰テストとして育てる）。
- QA の回答文はゴールデンセットに複製しない（採点時にシード元データから引く）。

## 採点

| 指標 | 方法 |
|---|---|
| 出典の一致（1位一致率・一致率・MRR） | 回答に付いた出典（`sources`）に正解出典が何位で含まれるか。出典を返さない古い agent_invitro では採点しない |
| 回答の正しさ（1〜5） | LLM 採点。模範解答の要点をどれだけ正しく含むか |
| 根拠への忠実さ（1〜5） | LLM 採点。回答時の参考情報（検索結果）に書かれていない断定がないか |
| 回答を控えたか | 定型の断り文言・出典なしの逆質問（決定的）と LLM の判定の OR。範囲外の質問では控えるのが正解 |

- 採点モデルは **Claude Opus 5.5**（Amazon Bedrock、Anthropic SDK の Bedrock Mantle クライアント）。`EVAL_JUDGE_MODEL_ID` で変更できる。
  安全分類器で拒否された場合は Claude Opus 4.8 で1回だけ再試行する。
- 採点の比較は、同じ採点モデル・同じ採点プロンプトの実行どうしに限る。`summary.md` は条件が同じ前回実行と自動で比較する。

## history.csv

1回の実行を1行にした記録です（`run` のたびに自動で追記）。列は実行 ID・日時・ゴールデンセットとそのハッシュ・方式・
リリース（`release_id`・commit・prompt_hash・モデル）・採点モデルと採点プロンプトのハッシュ、そして `summary.md` の
集計と同じ指標です。質問・回答の文は含めないので git で管理し、差分で推移を追います。

## runs/<日時>_<セット>_<方式>/ の中身

| ファイル | 内容 |
|---|---|
| `results.jsonl` | 1問1行。質問・回答・出典・各スコア・採点理由・`release_id`・応答時間 |
| `meta.json` | リリースの全要素（`/api/release`）・ゴールデンセットのハッシュ・採点モデルと採点プロンプトのハッシュ |
| `summary.md` | 集計、要確認の質問、同じ条件の前回実行との比較（悪化・改善した質問） |

## feedback/<日時>.jsonl の形式

1行が評価済みの回答1件です（👍/👎 のみ。未評価は含まない）。

| キー | 内容 |
|---|---|
| `key` | 重複除去用のキー（会話・順序・評価・理由・評価日時から計算） |
| `conversation_id` / `order` | 会話と、その中の回答の位置 |
| `evaluation` | `good`（👍）/ `bad`（👎） |
| `evaluation_comment` | 評価の理由（未入力なら null） |
| `evaluated_at` / `answered_at` | 評価・理由を最後に変更した日時 / 回答した日時 |
| `question` / `context` | 利用者の質問と、回答時に渡した参考情報（検索結果） |
| `answer` / `model` / `ask_mode` | 回答本文・モデル・方式（`pipeline` / `agentic`） |
| `release_id` / `release` | 回答を生成したリリースと、その内容（コミット・プロンプトのハッシュ・モデル・設定値） |

- 同じ回答でも、評価や理由を付け直すと新しい行として追記されます（変更の履歴が残る）。
- ADR-0099 導入前の評価には `release_id` / `ask_mode` / `evaluated_at` がありません（null）。
