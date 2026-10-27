# evals/ — 評価ランナーと評価結果

回答品質の改善ループ（ADR-0099）で使う評価ランナーと、その結果を置くディレクトリです。
結果はリポジトリに残し、Claude Code に読ませて原因分析・修正案作成に使います。

```
evals/
  eval.bat            評価ランナーの呼び出し口（chatbot-evals イメージで python -m runner を実行）
  Dockerfile          評価ランナーのイメージ（python + Anthropic SDK + Claude Code）。eval.bat が毎回 build（キャッシュで即時）
  .env.example        設定の雛形 → evals/.env にコピーして記入（Git 管理外）
  runner/             評価ランナー本体
  judge_prompts/      LLM 採点のプロンプト（answer.md）
  judge_prices.json   採点モデルの単価表（採点費用の概算に使う。ADR-0100）
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
3. LLM 採点（`run`）は既定で `terraform/.env` の AWS 認証情報で Amazon Bedrock を呼ぶ（deploy と同じ）。
   Claude Code のサブスクリプションで採点する場合は、下の「採点の実行方法」を参照。
4. 採点の模範解答はシード元データから引くため、`terraform\dvc.bat pull` 済みであること（ADR-0097）。

## コマンド

| コマンド | 内容 |
|---|---|
| `evals\eval.bat pull-feedback` | チャット画面で付けた 👍/👎・理由・リリースの増分を `evals/feedback/<日時>.jsonl` に保存する |
| `evals\eval.bat build-golden` | 初版のゴールデンセット `evals/golden/v1.csv` を作る（最初の1回だけ。既にあれば `--force` が必要） |
| `evals\eval.bat run` | ゴールデンセット（既定 v2、`--set v1` で旧版）を両方式（pipeline / agentic）で送り、採点して `evals/runs/` に保存する |
| `evals\eval.bat run --repeat 3` | 同じ構成を3回実行し、指標の平均とばらつきを `evals/runs/groups/<グループ ID>.md` に出す（**比較の基準と改善の判定はこれで取る**。費用は3倍） |
| `evals\eval.bat run --mode agentic --limit 5` | 1方式・先頭5問だけ試す（`--no-judge` で LLM 採点なし） |
| `evals\eval.bat compare <A> <B>` | 2つの結果を比較する。A・B は実行ディレクトリ名か、繰り返しのグループ ID。揺れを超える差だけを改善・悪化と判定する |
| `evals\eval.bat run --judge-backend claude-code` | 採点を Claude Code（サブスクリプション）で行う（既定は `evals/.env` の `EVAL_JUDGE_BACKEND`、無ければ bedrock） |
| `evals\eval.bat judge <実行> --only-missing` | 未採点の質問だけを同じ実行に書き足す（使用量の上限などで採点が途中で止まった続き） |
| `evals\eval.bat judge <実行> [--judge-backend ...]` | 保存済みの回答を全問採点し直し、新しい実行として保存する（採点方式・採点プロンプトの比較、較正） |

`snapshot`（ナレッジのスナップショット）は段階④で追加します。

## 揺れと繰り返し実行（`--repeat`）

回答（Amazon Nova）は temperature 0 でも毎回変わり、LLM 採点も揺れます。v2 を同じ構成で2回実行したところ
（`20261007-*` と `20261016-*`。間の変更はタイムアウトの調整のみ）、出典の一致率はほぼ同じでしたが、
回答の正しさは ±0.3、根拠への忠実さは ±0.4、回答すべき質問で控えた割合は ±0.1 程度動きました。
1回ずつの比較では、この揺れと改善の効果を区別できません。

- **基準を取るとき・改善を判定するときは `run --repeat 3`** で同じ構成を3回実行し、`compare <変更前のグループ ID> <変更後のグループ ID>` で比べる。
- 繰り返しの各回は通常の実行（`<日時>_<セット>_<方式>_r<回>`）として保存され、`meta.json` の `repeat.group` と
  `history.csv` の `repeat_group`・`repeat_index` で同じグループと分かる。各回の `summary.md` の前回比較は、同じグループの他の回を相手にしない。
- グループの集計（`runs/groups/<グループ ID>.md`）には、指標の平均 ± 標準偏差（最小〜最大）と、回ごとに結果が大きく変わった質問を出す。
- `compare` の判定:
  - **指標**: 差が「標準誤差の2倍」（両側のばらつきと回数から計算）を超えたときだけ改善・悪化とする。片側が1回だけなら、もう片側のばらつきで代用する。両側とも1回なら判定しない。
  - **質問**: 片側の全回が、もう片側の全回より良い（悪い）ときだけ改善（悪化）とする。値は、回答すべき質問は正しさ（1〜5、控えたら 1）、範囲外の質問は控えたら 5・答えたら 1。
- 出典の一致率は揺れが小さいため、検索の改善（重複除去・タグの重みなど）は出典の指標を主に見る。

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

- 版ごとの内容と変更理由は `golden/README.md`。現在の既定は **v2（25問）**。v1 は正解設定の誤りを含むため、比較の基準にしない。
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
- 採点の比較は、同じ採点モデル・同じ採点プロンプト・同じ採点方式の実行どうしに限る。`summary.md` は条件が同じ前回実行と自動で比較する。

### 採点の実行方法（ADR-0101）

| 方式 | 呼び出し | 認証 | 費用 |
|---|---|---|---|
| `bedrock`（既定） | Anthropic SDK の Bedrock Mantle クライアント（`anthropic.claude-opus-5-5`） | `terraform/.env` の AWS 認証情報 | AWS の従量課金 |
| `claude-code` | Claude Code の非対話モード `claude -p`（`claude-opus-5-5`） | `evals/.env` の `CLAUDE_CODE_OAUTH_TOKEN` | サブスクリプションの使用量 |

`claude-code` を使うとき:

1. ホストで `claude setup-token` を実行し、表示されたトークンを `evals/.env` の `CLAUDE_CODE_OAUTH_TOKEN` に書く（発行した本人だけが使う）。
2. `evals\eval.bat run --judge-backend claude-code`（または `evals/.env` に `EVAL_JUDGE_BACKEND=claude-code`）。
   Claude Code はランナーのイメージに入っている（`evals/Dockerfile`）。

- 呼び出しは `claude --safe-mode -p --tools "" --max-turns 1 --no-session-persistence --system-prompt-file <採点プロンプト>
  --model claude-opus-5-5 --effort medium --output-format json`。採点プロンプトと入力は Bedrock と同じ。
- 採点の前に `claude auth status` で、サブスクリプションの認証（`oauth_token` / `claude.ai`）であることを確かめる。
  `ANTHROPIC_API_KEY`・`CLAUDE_CODE_USE_BEDROCK`・AWS の認証情報などは、課金経路が変わらないよう `claude` に渡さない。
- **使用量の上限**に達したら、残りの質問を採点せずに止める（`summary.md` に未採点の件数が出る）。リセット後に
  `evals\eval.bat judge <実行> --only-missing` で続きを採点する。トークンが無効な場合（401）も最初の質問で止める。
- 費用欄は API 単価換算の値で、実際の請求額ではない。
- 自分の端末で手動実行する場合に限る。定期実行・CI・AWS 検証環境では `bedrock` を使う。
- 採点方式が違う実行どうしは前回比較で自動的に分かれる。切り替える前に、同じ実行を両方式で採点（`judge`）して差を確かめる。

### 採点のトークン数と費用（ADR-0100）

- 採点の呼び出しごとに `response.usage` を読み、1問分の合計を `results.jsonl` に残す（`judge_calls`・`judge_input_tokens`・
  `judge_output_tokens`・`judge_thinking_tokens`・`judge_cache_write_tokens`・`judge_cache_read_tokens`・`judge_cost_usd`）。
  拒否・JSON 読み取り失敗の再試行と Opus 4.8 へのフォールバックも、課金されるので数える。
- 出力トークンには思考トークンが含まれる（Opus 5.5 は思考を止められない）。`judge_thinking_tokens` はその内数
  （`usage.output_tokens_details.thinking_tokens`）で、effort を変えたときの影響を見るために残す。
- 費用は `judge_prices.json` の単価（USD / 100万トークン）で計算した**概算**。初版は Anthropic API の定価なので、
  Amazon Bedrock の単価を [料金ページ](https://aws.amazon.com/bedrock/pricing/) で確認し、差があれば書き換えてコミットする。
  単価表に無いモデルを使った場合、費用は空欄になる（トークン数は残る）。
- 回答側（Amazon Nova・Titan Embeddings）の費用は含まない。回答側は Bedrock のモデル呼び出しログから集計する。
- 2026-10-07 以前の実行には記録が無い（空欄）。

## history.csv

1回の実行を1行にした記録です（`run` のたびに自動で追記）。列は実行 ID・日時・ゴールデンセットとそのハッシュ・方式・
リリース（`release_id`・commit・prompt_hash・モデル）・採点モデルと採点プロンプトのハッシュ・採点方式（`judge_backend`）、そして `summary.md` の
集計と同じ指標、採点のトークン数と概算費用（`judge_calls` 〜 `judge_cost_usd_per_question`）です。
質問・回答の文は含めないので git で管理し、差分で推移を追います。列が増えたときは、次の `run` で既存の行を残したまま
新しいヘッダーに書き直します（既存行の新しい列は空欄）。

## runs/<日時>_<セット>_<方式>/ の中身

| ファイル | 内容 |
|---|---|
| `results.jsonl` | 1問1行。質問・回答・出典・回答時の参考情報（`context`。再採点に使う）・各スコア・採点理由・`release_id`・応答時間・採点のトークン数と概算費用 |
| `meta.json` | リリースの全要素（`/api/release`）・ゴールデンセットのハッシュ・採点モデル・採点プロンプトのハッシュ・採点方式（`claude-code` は CLI の版も）・費用の概算に使った単価表（`judge_prices`）・採点が途中で止まった場合の理由と未採点数（`judge_incomplete`）・再採点の元の実行（`answers_from`） |
| `summary.md` | 集計、採点のトークン数と概算費用、要確認の質問、同じ条件の前回実行との比較（悪化・改善した質問） |

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

## 構成（上の一覧に無いもの）

| 名前 | 説明 |
|---|---|
| [`runner/`](runner/README.md) / [`tests/`](tests/README.md) / [`judge_prompts/`](judge_prompts/README.md) / [`golden/`](golden/README.md) | 各ディレクトリのファイル一覧はそれぞれの README を参照 |
| [`runs.dvc`](runs.dvc) / [`feedback.dvc`](feedback.dvc) | `runs/`・`feedback/` の DVC ポインタ（内容ハッシュ）。上の「評価データの管理」の手順で更新する |
| [`.gitignore`](.gitignore) | DVC が展開する `runs/`・`feedback/` を git の対象外にする（`dvc add` が生成） |
