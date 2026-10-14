# ADR-0101: ゴールデンセット評価の LLM 採点を、Claude Code の非対話モード（`claude -p`）でも実行できるようにする

- ステータス: Proposed（実装済み。実際のトークンでの検証と社内確認の後に Accepted にする。末尾の「Accepted にする前に確かめること」）
- 日付: 2026-10-14
- 関連: ADR-0031（Bedrock 接続）、**ADR-0099（回答品質の改善ループ。§5 の評価ランナーと LLM 採点）**、**ADR-0100（採点のトークン数と概算費用の記録）**

## コンテキスト

ADR-0099 §5 の評価ランナー（`evals\eval.bat run`）は、ゴールデンセットの回答を Claude Opus 5.5 で採点する。採点は、Anthropic SDK の `AnthropicBedrockMantle` から Amazon Bedrock を呼んでいる。費用は AWS アカウントに従量課金で計上される（ADR-0100 で、トークン数と概算費用を記録するようにした）。

一方、開発者は Claude Code をサブスクリプション（Pro / Max / Team 等のプラン）で使っている。サブスクリプションには使用量の上限があるが、上限まで使い切らない期間も多い。**採点をサブスクリプションの使用量で賄えれば、使っていない枠を活かしつつ、AWS の従量課金を減らせる。** 評価の回数を増やしやすくなり、改善ループ（ADR-0099）を速く回せる。

### `claude -p` で何ができるか（2026-10-14 時点の公式ドキュメントで確認）

| 項目 | 内容 | 出典 |
|---|---|---|
| システムプロンプトの置き換え | `--system-prompt-file <path>` で既定のプロンプトを丸ごと置き換えられる（`-p` でも有効） | cli-reference |
| ツールの無効化 | `--tools ""` で組み込みツールを全て外す。`--max-turns 1` で1往復に限る | cli-reference |
| モデル・effort | `--model <ID または別名>`、`--effort low〜max`。環境変数 `CLAUDE_CODE_EFFORT_LEVEL` は `--effort` より優先される | cli-reference / env-vars / model-config |
| 周辺設定の除外 | `--safe-mode` で CLAUDE.md・自動メモリ・スキル・プラグイン・フック・MCP サーバーを読まない。認証とモデル選択は通常どおり | cli-reference |
| セッションを残さない | `--no-session-persistence` | cli-reference |
| 結果の形式 | `--output-format json` で `result`（応答本文）・`usage`（入力・出力・キャッシュのトークン数）・モデル別の使用量・`total_cost_usd`（API 単価での換算。請求額ではない）が返る | headless / agent-sdk cost-tracking |
| 無人実行の認証 | `claude setup-token` で発行した OAuth トークン（有効期限1年）を `CLAUDE_CODE_OAUTH_TOKEN` に渡す。`claude auth status` の `authMethod` で認証方式を確かめられる | authentication |

使う上での注意点も分かった。

- **`--bare`（設定を最小にするモード）はサブスクリプションの認証を読まない。** API キーが必須になるため使えない。代わりに `--safe-mode` を使う。
- **`ANTHROPIC_API_KEY` が環境にあると、`-p` では必ずそちらが使われる。** 課金が API に黙って切り替わる。認証の優先順位はクラウド事業者の環境変数（`CLAUDE_CODE_USE_BEDROCK` 等）→ `ANTHROPIC_AUTH_TOKEN` → `ANTHROPIC_API_KEY` → `CLAUDE_CODE_OAUTH_TOKEN` の順。
- **使用量の上限に達すると、リセットまで呼び出しが失敗する。** `-p` での終了コードやエラーの形は文書化されていない。
- **利用規約上の位置付け。** 法務ページには、サブスクリプションの OAuth 認証は「Claude Code の通常の利用」を想定していると書かれている。また、Claude の機能と連携する製品やサービスを作る開発者は API キーを使うべき、ともある。開発者が自分の端末で手動で回す評価は通常の利用の範囲と考えるが、定期実行や他者向けのサービスにする場合は当たらない。
- システムプロンプトを置き換えたとき、ツール定義や環境情報などが他に送られるかどうかは文書化されていない。

### 現在の評価ランナーの制約

- 採点は回答の収集と同じループの中で行う（`run.py`）。採点だけを後からやり直す手段がない。
- `results.jsonl` に、採点の入力に使う回答時の参考情報（`context`）を保存していない。そのため、回答を集め直さないと再採点できない。
- ランナーは Docker コンテナ（`chatbot-evals` イメージ）で動き、`claude` CLI は入っていない。

## 決定

**採点の実行方法（バックエンド）として、既存の Bedrock に加えて Claude Code（`claude -p`、サブスクリプション認証）を選べるようにする。あわせて、回答の収集と採点を分けて、採点だけを後から実行・やり直しできるようにする。既定は、較正（§6）を終えるまで Bedrock のままにする。**

### 1. バックエンドの切り替え

- `evals/.env` の `EVAL_JUDGE_BACKEND=bedrock|claude-code` で選ぶ（コマンドライン引数 `--judge-backend` でも上書きできる）。既定は `bedrock`。
- `Judge` は、採点プロンプトの組み立て・JSON の読み取り・スコアの検証・トークン数の集計を共通に保ち、呼び出し部分だけを差し替える。採点プロンプト（`judge_prompts/answer.md`）とユーザー側の入力（JSON）は両方式で同一にする。

### 2. `claude -p` の呼び出し方

1問ごとに新しいプロセスで、次の形で呼ぶ。入力の JSON は標準入力で渡す（コマンドラインの長さ制限と、引数のエスケープの問題を避けるため）。

```
claude --safe-mode -p --tools "" --max-turns 1 --no-session-persistence \
  --system-prompt-file judge_prompts/answer.md \
  --model claude-opus-5-5 --effort medium --output-format json
```

- モデルと effort は Bedrock 方式と同じ値（Opus 5.5・`medium`）を明示する。`CLAUDE_CODE_EFFORT_LEVEL` は `--effort` より優先されるため、子プロセスの環境から外す。
- 子プロセスの環境変数から、`ANTHROPIC_API_KEY`・`ANTHROPIC_AUTH_TOKEN`・`CLAUDE_CODE_USE_BEDROCK`・`CLAUDE_CODE_USE_VERTEX` などを外す。ランナーは AWS の認証情報を環境に載せるため、Bedrock 経由に切り替わる経路を確実に断つ。
- 構造化出力（`--json-schema`）は使わない。Bedrock 方式と同じく、応答から JSON を読み取る。両方式で採点の条件をそろえるため。
- 拒否されたとき（安全分類器）は、JSON の `stop_reason` が `refusal` なら Bedrock 方式と同じく Opus 4.8 で1回だけ再試行する。`stop_reason` 自体は結果の JSON にあることを確かめたが（2.1.287）、拒否時の値は未確認。`refusal` 以外の値になる場合は、JSON を読み取れず採点不可として記録される。
- 結果の JSON の形は Claude Code 2.1.287 で確かめた。API の失敗時も `subtype` は `success` のままで、`is_error: true` と `api_error_status`（HTTP ステータス）が入る。思考トークンは `usage.output_tokens_details.thinking_tokens` に入る。

### 3. 認証と実行前の確認

- 開発者が `claude setup-token` でトークンを発行し、`evals/.env`（Git 管理外）の `CLAUDE_CODE_OAUTH_TOKEN` に書く。ランナーは `evals/.env` を読み（リポジトリはコンテナにマウントされている）、`claude` の子プロセスにだけ渡す。
- `claude` CLI は評価ランナーのイメージに公式のネイティブインストーラで入れる（`curl -fsSL https://claude.ai/install.sh | bash -s <版>`）。版はビルド引数 `CLAUDE_CODE_VERSION`（既定 `stable`）で固定でき、実際に使った版は採点のたびに `meta.json` の `judge.cli_version` に記録する。自動更新は `DISABLE_AUTOUPDATER=1` で止める。npm 版は Node.js 22 以上が要り、Python のイメージに入れるのが重いため採らない。
- 採点を始める前に `claude auth status` を実行し、`authMethod` が `oauth_token` / `claude.ai` 以外なら中止する。サブスクリプションのつもりで API 課金になる事故を防ぐ。
- `claude auth status` はトークンの有効性までは確かめない（無効なトークンでも `oauth_token` と表示される）。無効なトークンは最初の採点の 401 で分かるので、そこで採点を止める（§5）。

### 4. 回答の収集と採点を分ける

- `results.jsonl` に回答時の参考情報（`context`）を保存する。`runs/` は DVC 管理で git に入らないので、ナレッジ本文を含めてよい（ADR-0099 §5 と同じ扱い）。
- 新しいサブコマンド `evals\eval.bat judge <実行ディレクトリ名> [--judge-backend ...] [--only-missing]` を設ける。
  - `--only-missing`: 未採点の質問だけを採点し、**同じ実行**に書き足す。`history.csv` の同じ実行の行は置き換える。採点条件（モデル・プロンプト・方式）が元の実行と違う場合は中止する。
  - 付けない場合: 全問を採点し直し、**新しい実行ディレクトリ**に保存する（`meta.json` の `answers_from` に元の実行名を残す）。元の実行は書き換えない。較正（§6）や採点プロンプトの比較に使う。
  - 模範解答が変わらないよう、ゴールデンセットのファイルが実行時と同じ（sha256 が一致する）ことを確かめる。`context` を保存していない実行（本 ADR より前）は採点し直せない。
- `run` は従来どおり、回答の収集に続けて採点まで行う（`--no-judge` なら収集だけ）。

### 5. 使用量の上限に達したとき（と、認証に失敗したとき）

- 上限に達したことを示すエラー（`api_error_status` が 429、または「hit your … limit」などの文言）が返ったら、**残りの質問の採点をやめる**。それ以降の質問を「採点不可」で埋めない。
- 認証の失敗（401 / 403）も同じく、その時点で採点をやめる。以降の質問も全て失敗するため。
- 採点済みの分は保存し、`summary.md` に「採点が途中で止まった」ことと、未採点の件数を明記する。
- 上限のリセット後に `eval.bat judge <実行> --only-missing` で残りを採点する。
- 上限に達したときの実際の JSON（`api_error_status` と文言）は、まだ確かめていない。上の2つの条件のどちらにも当たらない場合は、その質問が「採点不可」になり、次の質問に進む。

### 6. 較正と、比較条件の分離

- `meta.json` の `judge` に `backend`（`bedrock` / `claude-code`）と CLI の版を加える。これにより、採点方式の違う実行どうしは前回比較（`find_previous`）で自動的に分かれる。比較の条件に CLI の版は含めない（版が上がるたびに比較が途切れるのを避けるため）。`backend` の記録が無い本 ADR より前の実行は `bedrock` として扱い、これまでの比較を続ける。
- `history.csv` に `judge_backend` 列を加える。
- 導入時に、同じ実行の回答を両方式で採点し（§4 の `judge` を使う）、質問ごとのスコアの差を `docs/improvements/` に記録する。差が採点の揺れ（同じ方式で2回採点したときの差）と同程度なら、既定を `claude-code` に切り替えることを検討する。切り替えたら、新しい基準の実行を取り直す。

### 7. トークン数と費用の記録（ADR-0100 との関係）

- `claude -p` の JSON の `usage` から、ADR-0100 と同じ欄（`judge_input_tokens` 等）を埋める。モデル別の使用量（`modelUsage`）が返るので、記録するモデル ID もそこから取る。1回の呼び出しで複数モデルの使用量が返っても、呼び出し回数は1回と数える。
- `judge_cost_usd` は `judge_prices.json` の単価で計算した **API 単価換算の値** とする。`claude-code` 方式では実際の請求額ではない（サブスクリプションの使用量として消費される）。`summary.md` では「API 単価換算」と明記する。CLI が返す `total_cost_usd` も API 単価での換算値で、同じものを二重に持つことになるため記録しない。
- Claude Code は独自のシステムプロンプトを置き換えても、他の情報を送る可能性がある（文書化されていない）。入力トークン数を Bedrock 方式と比べて、余分な入力が無いことを較正（§6）で確かめる。

### 8. 使ってよい範囲

- `claude-code` 方式は、**開発者が自分の端末で手動で実行する場合に限る。** 定期実行・CI・AWS 検証環境での実行（ADR-0099 §5 の将来の移行先）では Bedrock 方式を使う。
- トークンは発行した開発者本人のものとし、共有しない。

## 検討した代替案

- **このセッション（対話中の Claude Code）が直接採点する**
  - 追加の仕組みが最も少ない。
  - 一方で、対話中のセッションはゴールデンセットの経緯や過去の結果を知っており、独立した採点者にならない。同じ条件で繰り返せず、実行どうしの比較に使えない。不採用。
- **`--bare` と API キーで `claude -p` を呼ぶ**
  - 設定を最小にでき、規約上も明確。
  - 一方で、API 課金になるため、サブスクリプションの使用量を活かすという目的を満たさない。Bedrock を Anthropic API に替えるだけになる。不採用。
- **ホスト（Windows）で直接 `claude -p` を呼び、コンテナを使わない**
  - 開発者がログイン済みの Claude Code をそのまま使え、トークンの発行が要らない。
  - 一方で、ランナーの実行環境（Python の版・依存）がホストに依存する。ホストの Claude Code の設定やメモリが混ざる余地も増える。評価の再現性のため、コンテナに CLI を入れる方式を採る。不採用。
- **採点モデルを Sonnet 5.5 に替え、effort を下げて Bedrock の費用を減らす**
  - 仕組みは変わらない。
  - 費用は減るが、採点の質が変わるうえ、サブスクリプションの使用量を活かす目的には応えない。本 ADR とは独立に、較正の結果を見て検討できる。

## 結果・影響

- 開発者の Claude Code のサブスクリプション使用量で採点でき、AWS の従量課金を減らせる。採点だけのやり直しもできるようになり、採点プロンプトを変えたときに回答を集め直さずに比較できる。
- **受け入れるトレードオフ**
  - 使用量の上限に達すると採点が途中で止まり、リセットまで待つことになる。
  - 開発者の対話利用と使用量を取り合う。大きな評価は、使用量に余裕のある時間帯に回す。
  - 採点の入力（ナレッジ本文・回答）は、AWS 内の Bedrock ではなく Anthropic に直接送られ、契約しているプランの規約で扱われる。**社内のデータの扱いとして問題ないことを確認してから Accepted にする。**
  - `claude-code` 方式の費用欄は API 単価換算の値で、実際の請求額ではない。
- **変更が及ぶ範囲**: `evals/runner/judge.py`（呼び出し部分の分離と `claude -p` の実装）、`evals/runner/run.py`（`context` の保存、採点の分離）、`evals/runner/__main__.py`（`judge` サブコマンド・`--judge-backend`）、`evals/Dockerfile`（CLI の導入）、`evals/eval.bat`（使い方のコメント）、`evals/.env.example`、`evals/tests/`、`evals/README.md`。agent_invitro・AWS 構成・画面は変えない。

## Accepted にする前に確かめること

実装時（2026-10-14、Claude Code 2.1.287、コンテナ内）に確かめたこと:

- 上の呼び出し方のフラグは全て受け付けられる（`--system-prompt-file` と `--max-turns` は `--help` に出ないが有効）。
- `claude auth status` は JSON を返し、`CLAUDE_CODE_OAUTH_TOKEN` を渡すと `authMethod` が `oauth_token` になる。ランナーの環境に `ANTHROPIC_API_KEY` があっても、子プロセスからは外れる。
- 無効なトークンでは、`--safe-mode` を付けた `-p` の呼び出しが API まで届き、401 を `is_error: true`・`api_error_status: 401` として返す。

残っていること:

1. 有効なトークンで1問を採点し、`--safe-mode` とサブスクリプション認証で採点が通ることを確かめる。
2. `--system-prompt-file` と `--tools ""` を指定したとき、余分な入力トークンがどれだけ増えるか（Bedrock 方式と同じ入力での比較）。
3. 使用量の上限に達したときと、拒否されたときの JSON（`api_error_status`・文言・`stop_reason`）。
4. 採点の入力を Anthropic に直接送ることについての社内確認と、利用するプランの規約・利用条件（2026-10-07 に告知された、Max・Team プランに含まれる月次の API クレジットの扱いを含む）。
