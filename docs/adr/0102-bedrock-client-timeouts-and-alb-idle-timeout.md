# ADR-0102: Bedrock クライアントの読み取りタイムアウトを短くし、admin_ui の ALB のアイドルタイムアウトを延ばす

- ステータス: Proposed（実装済み。デプロイ後の確認（末尾）を終えたら Accepted にする）
- 日付: 2026-10-14
- 関連: ADR-0031（Bedrock 接続）、ADR-0041（admin_ui のネットワーク配置・ALB）、ADR-0043 / ADR-0045（agent_invitro の HTTP サービス化・admin_ui 経由のチャット）、ADR-0088 / ADR-0089（Agentic 回答生成・`/ask-*`）、ADR-0095（常駐4サービスの1タスク集約・VPC エンドポイントの単一 AZ 化）、ADR-0099（評価ランナー）

## コンテキスト

2026-10-14 14:36（JST）、評価ランナー（`evals\eval.bat run --mode agentic --limit 3`）で、3問中2問が admin_ui の ALB から **HTTP 504 Gateway Time-out** を返した。どちらも応答時間は約 60.4 秒で、ALB のアイドルタイムアウトの既定値（60 秒）と一致する。3問目は 5.8 秒で正常に返った。

agent_invitro のログ（`/ecs/agent_invitro`）と Bedrock のモデル呼び出しログを突き合わせると、次のことが分かった。

| 呼び出し | agent_invitro が呼び始めた時刻（UTC） | Bedrock に届いた時刻 | Bedrock での処理時間 |
|---|---|---|---|
| 1問目のタグ分類（tag_selector_mcp） | 05:36:10 | 05:37:11 | 0.57 秒 |
| 1問目の十分性評価（agent_invitro） | 05:37:13 | 05:38:13 | 0.55 秒 |
| 2問目の回答生成（agent_invitro） | 05:37:14 | 05:38:14 | 2.5 秒 |
| 3問目の全呼び出し | ― | すぐに届いた | 0.5〜1.8 秒 |

- **Bedrock の処理は速く、呼び出しが Bedrock に届くまでに約 60 秒かかっていた。** 60 秒は boto3（botocore）の読み取りタイムアウトの既定値と一致する。1回目の通信が応答を待ったまま 60 秒でタイムアウトし、自動の再試行で成功したと考えられる。
- 止まったのは、別々の boto3 クライアント（タグ分類・十分性評価・回答生成）でそれぞれ1回ずつで、その後は速い。各モジュールは起動時にクライアントを作り、プロセスが動いている間使い続ける。
- 前回の利用は 2026-10-07 で、サービスは1週間使われていなかった。

**推定される原因**: 長く使われていない間に、クライアントが接続プールに持っている HTTPS 接続が途中経路（Bedrock の Interface VPC エンドポイント等）で切られた。クライアントはそれに気づかず古い接続で送信し、応答が来ないまま読み取りタイムアウト（60 秒）まで待ってから、新しい接続で再試行した。ログの形と合うが、再現による確認はまだしていない（「確認」参照）。

### 待ち時間の連鎖（変更前）

| 区間 | タイムアウト | 設定箇所 |
|---|---|---|
| 評価ランナー → admin_ui | 180 秒 | `evals/runner/client.py` |
| ブラウザ・評価ランナー → **ALB → admin_ui** | **60 秒（既定）** | `terraform/modules/admin-ui-alb`（未設定） |
| admin_ui → agent_invitro | 120 秒 | `AGENT_INVITRO_TIMEOUT`（`web_backend/src/main/config.py`） |
| agent_invitro・MCP → Bedrock（1回の読み取り） | **60 秒（既定）**、再試行あり | boto3 の既定 |

admin_ui は agent_invitro を 120 秒待つ設計なのに、その手前の ALB が 60 秒で打ち切っている。さらに、切れた接続に1回当たるだけで 60 秒を使い切る。

## 決定

**Bedrock クライアントに、短い接続・読み取りタイムアウトと再試行の設定を明示する。あわせて、admin_ui の ALB のアイドルタイムアウトを、admin_ui → agent_invitro の待ち時間より長くする。**

### 1. Bedrock クライアントのタイムアウトと再試行

botocore の `Config` を、リクエストの処理経路にある全ての `bedrock-runtime` クライアントに渡す。

| 用途 | 対象 | 接続 | 読み取り | 再試行 |
|---|---|---|---|---|
| 出力が短い呼び出し（short） | タグ分類（tag_selector_mcp）、埋め込み（knowledge_mcp）、言い換え・十分性評価・逆質問・要約（agent_invitro） | 5 秒 | **20 秒** | standard モード・最大 3 回 |
| 回答生成（generate） | `GenerateAnswerLLMBedrock`（agent_invitro） | 5 秒 | **60 秒** | standard モード・最大 3 回 |

- 回答生成は出力が長くなりうる（`max_tokens` 4096）ため、読み取りを 60 秒に残す。それ以外は応答が数秒で返るため 20 秒にする。切れた接続に当たったときの待ちは、最大でも読み取りタイムアウトの分で済む。
- 再試行は standard モードにする。読み取りタイムアウトを含む一時的な失敗が再試行の対象になり、待ち時間に指数バックオフが入る。
- 環境変数で上書きできるようにする: `BEDROCK_CONNECT_TIMEOUT_SEC` / `BEDROCK_READ_TIMEOUT_SEC` / `BEDROCK_GENERATE_READ_TIMEOUT_SEC`（agent_invitro のみ）/ `BEDROCK_MAX_ATTEMPTS`。既定値で運用し、Terraform のタスク定義には追加しない。
- 実装の置き場所:
  - agent_invitro: `src/bedrock_client.py` の `make_bedrock_client(region, kind)` に集め、5つのモジュール（`generate` / `condense` / `clarify` / `summarize` / `llm_tasks/assess/bedrock`）から使う。
  - tag_selector_mcp・knowledge_mcp: クライアントを作る箇所が1つずつなので、それぞれのモジュール内に設定関数を置く（サービスごとに別パッケージ・別イメージのため、共通モジュールは作らない）。

### 2. admin_ui の ALB のアイドルタイムアウトを 150 秒にする

- `terraform/modules/admin-ui-alb` に変数 `idle_timeout`（既定 150 秒）を設け、`aws_lb` に設定する。
- 150 秒は、admin_ui → agent_invitro の 120 秒より長く、評価ランナーの 180 秒より短い。agent_invitro が遅いときは admin_ui の側でタイムアウトし、ALB の 504 ではなくアプリのエラーとして返る。

### 待ち時間の連鎖（変更後）

```
評価ランナー 180 秒 ＞ ALB 150 秒 ＞ admin_ui → agent_invitro 120 秒 ＞ Bedrock 1回の読み取り 20 秒（回答生成は 60 秒）
```

10-14 と同じ状況（1問目でタグ分類と十分性評価がそれぞれ切れた接続に当たる）でも、待ちは約 120 秒から約 40 秒に縮み、ALB の制限にも admin_ui の制限にも収まる。

### 対象外

- **web_backend の Bedrock クラス**（`GenerateAnswerLLMBedrock` / `SummarizeLLMBedrock` / `FormatQueryToEmbedBedrock`）は、`llm/__init__.py` から公開されているだけで、どこからも使われていない（admin_ui のチャットは agent_invitro に委ねている）。今回は変えない。
- **agent_invitro の `build_llm`（`ChatBedrockConverse`）** は開発用の ipython からしか使われていないため、変えない。
- **評価ランナーの採点（Anthropic SDK・`claude -p`）** は別の経路で、今回の問題とは関係しない。

## 検討した代替案

- **ALB のアイドルタイムアウトだけを延ばす**
  - 変更は Terraform の1行で済む。
  - 一方で、切れた接続に当たるたびに 60 秒待つことは変わらず、1つのリクエストで複数のクライアントが当たると 120 秒を超えて admin_ui 側でタイムアウトする（10-14 の1問目は2回当たって約 120 秒だった）。利用者の待ち時間も長いまま。単独では採らない。
- **リクエストのたびにクライアントを作り直す（接続を使い回さない）**
  - 切れた接続に当たらなくなる。
  - 一方で、毎回 TLS の接続確立が入り、通常時の応答が遅くなる。認証情報の取得も繰り返す。不採用。
- **TCP キープアライブで接続を保つ**（botocore の `tcp_keepalive=True` と、タスク定義の `systemControls` で `net.ipv4.tcp_keepalive_time` を短くする）
  - 途中経路で接続が切られること自体を防げる可能性がある。
  - 一方で、Fargate でこのカーネルパラメータを設定できるかと、VPC エンドポイントのアイドル判定にキープアライブが効くかを確かめていない。効果の確認がタイムアウトの短縮より難しい。今回の対策でも 504 が残る場合に検討する。
- **定期的に Bedrock を呼んで接続を温めておく**
  - 切れた接続を常に作らない。
  - 一方で、使っていない時間にも Bedrock の呼び出し料が発生し、仕組みも増える。検証環境の費用を下げる方針（ADR-0095）に反する。不採用。

## 結果・影響

- 長く使っていなかった後の最初の質問でも、ALB の 504 にならなくなる見込み。切れた接続に当たったときの待ちは、1回あたり 60 秒から 20 秒（回答生成は 60 秒のまま）に縮む。
- **受け入れるトレードオフ**
  - 出力が短い呼び出しが、本当に 20 秒以上かかる場合（Bedrock 側の遅延など）は、タイムアウトして再試行になる。再試行を含めても失敗すれば、従来どおり各モジュールの失敗時の扱い（十分性評価の縮退など）になる。値は環境変数で戻せる。
  - 1つのリクエストで多くのクライアントが同時に切れた接続に当たると、合計の待ちが admin_ui の 120 秒を超えうる（言い換え・タグ分類・埋め込み・十分性評価で各 20 秒、回答生成で 60 秒の場合に 140 秒）。この場合は admin_ui がタイムアウトのエラーを返す（ALB の 504 ではない）。
  - ALB が 150 秒まで接続を保つため、遅い応答に対して接続を長く持つ。社内からのみ到達できる検証環境のため影響は小さい。
- **変更が及ぶ範囲**: `agent_invitro/src/bedrock_client.py`（新規）と5つのモジュール、`tag_selector_mcp/src/tag_selector_mcp/infrastructure/llm/bedrock.py`、`knowledge_mcp/src/knowledge_mcp/mcp/server.py`、`terraform/modules/admin-ui-alb`（`idle_timeout`）、各サービスのテスト。画面・API の契約・DB は変えない。
- **デプロイ**: agent_invitro・tag_selector_mcp・knowledge_mcp のイメージを作り直し、app 構成を apply する（ALB の属性の変更は ALB の再作成を伴わない）。

## 確認（デプロイ後）

1. ALB の属性 `idle_timeout.timeout_seconds` が 150 になっていること。
2. サービスを 10 分以上使わずに置いた後、評価ランナーで数問を送り、504 にならないこと。
3. そのときのログで、切れた接続に当たった呼び出しの待ちが約 20 秒（回答生成は約 60 秒）になっていること。agent_invitro が呼び始めた時刻と、Bedrock のモデル呼び出しログの時刻の差で確かめる。待ちが起きない場合は、推定した原因（切れた接続）が当たらなかったことになるので、本 ADR の「推定される原因」を見直す。
