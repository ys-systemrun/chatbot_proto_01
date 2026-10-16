# ADR-0100: ゴールデンセット評価の LLM 採点のトークン数と概算費用を、呼び出しごとの `response.usage` から記録する

- ステータス: Accepted
- 日付: 2026-10-07
- 関連: ADR-0031（Bedrock 接続）、**ADR-0099（回答品質の改善ループ。§5 の評価ランナーと LLM 採点に記録を足す）**

## コンテキスト

ADR-0099 §5 の評価ランナー（`evals\eval.bat run`）は、ゴールデンセットの各質問について次の2種類の Bedrock 呼び出しを行う。

| 呼び出し | 経路 | モデル |
|---|---|---|
| 回答生成（タグ分類・検索・十分性判定・回答） | agent_invitro → `bedrock-runtime`（Converse / InvokeModel） | Amazon Nova 2 Lite・Titan Text Embeddings v2 |
| LLM 採点 | 評価ランナー → Anthropic SDK の `AnthropicBedrockMantle`（Messages API） | Claude Opus 5.5（拒否時は Opus 4.8） |

2026-10-07 の v2 評価（`20261007-140240_v2_agentic`）について、Bedrock のモデル呼び出しログ（CloudWatch Logs）から費用を概算しようとしたところ、次のことが分かった。

1. **呼び出しログに採点の呼び出しが含まれない。** ログにあったのは Nova と Titan の呼び出しだけで、Claude Opus の呼び出しは1件も無かった。回答側は1問あたり Nova 入力 約4,260・出力 約460 トークン（約 $0.0024）と計算できたが、採点側は計算できない。
2. **出力トークンを後から推定できない。** 採点は `output_config.effort = "medium"` で呼ぶ。Opus 5.5 は思考を止められず、思考トークンは `output_tokens` として課金される。思考の中身は応答に含まれず、`results.jsonl` に残る `judge_reason` からは量を推定できない（`max_tokens` は 16,000）。
3. **使用量を捨てている。** `judge.py` は `response.usage` を読んでいない。拒否時のフォールバックや JSON 読み取り失敗時の再試行で1問の呼び出し回数が増えても、記録が残らない。

採点にかかる費用は、評価をどの頻度・規模で回せるかの判断材料になる。採点モデルや effort、採点プロンプトを変えたときの費用の変化も、品質の変化と並べて見たい。

## 決定

**採点の呼び出しごとに `response.usage` を読み、1問分を合計して `results.jsonl` に残す。費用はリポジトリ内の単価表で概算し、`summary.md` と `history.csv` に集計を載せる。**

### 1. 記録する値（`results.jsonl` の1問1行に追加）

| キー | 内容 |
|---|---|
| `judge_calls` | その質問の採点で応答が返った呼び出しの回数（拒否・JSON 読み取り失敗の再試行、Opus 4.8 へのフォールバックを含む） |
| `judge_input_tokens` / `judge_output_tokens` | `usage.input_tokens` / `usage.output_tokens` の合計（出力は思考トークンを含む） |
| `judge_thinking_tokens` | `usage.output_tokens_details.thinking_tokens` の合計（`judge_output_tokens` の内数。費用は出力として計算済みで、effort の影響を見るために分けて残す） |
| `judge_cache_write_tokens` / `judge_cache_read_tokens` | `usage.cache_creation_input_tokens` / `usage.cache_read_input_tokens` の合計 |
| `judge_cost_usd` | 呼び出しごとに、そのモデルの単価で計算した概算費用の合計 |

- 拒否された応答や JSON を読めなかった応答も課金されるため、採点が成功したかどうかに関わらず数える。API エラーで応答が返らなかった呼び出しは数えない（使用量を取得できないため）。
- 採点しなかった質問（`--no-judge`、回答側のエラー）は `None` のままにする。0 と区別し、導入前の実行の結果も「記録なし」として扱う。

### 2. 単価表 `evals/judge_prices.json`

- モデル ID ごとに `input` / `output` / `cache_write` / `cache_read`（USD / 100万トークン）と、単価の出典・確認日（`source`）を持つ。
- 初版は Anthropic API の定価（Opus 5.5: $4 / $20、Opus 4.8: $5 / $25）を入れる。**Bedrock の単価は別に定められるため、AWS の料金ページで確認して差があれば書き換える。** 費用は「概算」として扱い、正確な請求額は AWS の請求で確かめる。
- 単価表に無いモデルの呼び出しが1回でもあれば、その質問と実行全体の費用は `None` にする（一部だけの合計を実額と取り違えないため）。トークン数は常に記録する。
- 実行時に使った単価表は `meta.json` の `judge_prices` に保存し、後から費用の根拠を確かめられるようにする。比較条件の `judge`（採点モデル・effort・採点プロンプト）には含めない。単価を書き換えるたびに前回実行との比較が途切れるのを避けるため。

### 3. 集計の出力

- `summary.md` に「採点のトークン数と概算費用」の節を設ける。呼び出し回数・各トークン数・概算費用・採点した1問あたりの概算費用を載せる。
- `history.csv` の末尾に同じ8列（`judge_calls` 〜 `judge_cost_usd_per_question`）を追加する。列が増える前の `history.csv` は、次の追記時に新しいヘッダーで書き直す（既存行の新しい列は空欄）。
- 品質の指標（`METRIC_LABELS`）とは分ける。前回実行との比較で、費用の増減を「悪化」「改善」として質問単位の判定に混ぜないため。

### 4. 対象外

- **回答側（Nova・Titan）のトークン数は今回は記録しない。** agent_invitro の応答に使用量が含まれず、記録するには agent_invitro の API 契約を変える必要があるため。回答側は Bedrock のモデル呼び出しログから集計できる。必要になったら別 ADR で扱う。
- 採点のプロンプトキャッシュ（採点プロンプトは全問共通の system なので、キャッシュの効果が見込める）は、記録を取ってから費用の大きさを見て判断する。キャッシュ系のトークン数を記録する欄は、導入時に効果を確かめられるよう先に用意しておく。

## 検討した代替案

- **CloudWatch メトリクス（`AWS/Bedrock` の `InputTokenCount` / `OutputTokenCount`）を実行時間帯で合計する**
  - コードを変えずに済む。
  - 一方で、Mantle 経由の呼び出しがこのメトリクスに出るかが確かめられていない。AWS アカウントは他プロジェクトと共用で、同じ時間帯の別の呼び出しと分けられない。質問単位の内訳も取れない。不採用（実行全体の突き合わせに使うのは構わない）。
- **Cost Explorer / CUR で、Opus の使用タイプ別の金額を見る**
  - 実際の請求額が分かる。
  - 一方で、反映が1日ほど遅れ、実行単位・質問単位には分けられない。共用アカウントのため、他の Opus 利用と混ざる。請求額との突き合わせ用として残し、日々の記録には使わない。不採用。
- **`count_tokens` で入力トークンを数え、出力は採点理由の長さから推定する**
  - 過去の実行にもさかのぼって適用できる。
  - 一方で、思考トークンが見えないため出力の推定が大きく外れうる。出力単価は入力の5倍で、費用の大半を占める可能性がある。不採用。
- **費用を記録せず、トークン数だけを残す**
  - 単価の管理が要らない。
  - 一方で、モデルごとの単価の違い（フォールバックの Opus 4.8 は Opus 5.5 より高い）を毎回手で計算することになる。単価表をリポジトリに置き、計算に使った単価を `meta.json` に残せば、後から再計算もできる。不採用。

## 結果・影響

- 次回の `eval.bat run` から、採点の費用が1問単位・実行単位で残る。品質の指標と同じ `history.csv` の行で推移を追える。
- 採点モデル・effort・採点プロンプトを変えたときに、品質と費用の両方の変化を比べられる。
- 導入前の実行（2026-10-07 以前）の採点費用は分からないまま残る。
- **変更が及ぶ範囲**: `evals/runner/judge.py`（使用量の取得・概算費用）、`evals/runner/scoring.py`（集計）、`evals/runner/run.py`（`results.jsonl`・`meta.json`・`summary.md`・`history.csv`）、`evals/judge_prices.json`（新規）、`evals/tests/test_run.py`、`evals/README.md`。agent_invitro・AWS 構成・画面は変えない。
- **運用**: 単価が変わったら `evals/judge_prices.json` を書き換えてコミットする。過去の実行の費用は、`results.jsonl` のトークン数と、その時点の `meta.json` の単価表から再計算できる。
