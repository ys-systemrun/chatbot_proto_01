# ADR-0099: 回答品質の改善ループ — 回答をリリース（コード・プロンプト・データ・モデル）に結び付け、ゴールデンセット評価と人手評価をリポジトリへ持ち帰る

- ステータス: Accepted（段階①実装済み）
- 日付: 2026-10-06
- 関連: ADR-0031（Bedrock 接続）、ADR-0043 / ADR-0045（agent_invitro の HTTP サービス化・admin_ui 経由のチャット）、ADR-0044（conversation DB）、ADR-0047 / ADR-0066（全データエクスポート・インポート）、ADR-0048〜0050（検証機能。検索のみを対象とする）、ADR-0085 / ADR-0088 / ADR-0089（condense・Agentic 回答生成・`/ask-*` の併存）、ADR-0087（評価済みメッセージ画面）、**ADR-0097（ナレッジデータの DVC 管理。本ADRが「評価ループ側の別ADR」として持ち越し事項を引き取る）**、ADR-0098（命名整理）

## コンテキスト

このチャットボットは、次のループで回答品質を改善していきたい。

1. ここ（ローカル + Claude Code）でナレッジデータ・プロンプト・コードを改善する
2. AWS 検証環境へデプロイする
3. Bedrock を使ったチャットで試し、評価する
4. 評価結果をここへ持ち帰り、原因を分析して次の改善につなげる

ADR-0097 で、シード元データの版（`KB_DATA_VERSION`）をデプロイ先まで届けられるようになった。しかし、ループの 3→4 にはまだ次の穴がある。

| # | 穴 | 現状 |
|---|---|---|
| 1 | **回答がどの版から出たか分からない** | assistant メッセージ（`message`）に残るのは `model` と `input`（LLM へ渡したプロンプト本文）だけ。コードの版、プロンプトの版、ナレッジの状態、`/ask-pipeline` と `/ask-agentic` のどちらで答えたかが記録されない |
| 2 | **ナレッジ DB の中身はシード元データの版と一致しない** | デプロイ後に全データインポート（ADR-0066）や管理画面での編集（QA・タグ・言い換え・`is_searchable`）が入る。`KB_DATA_VERSION` はシード元データの版でしかなく、回答時点の DB の状態を表せない |
| 3 | **プロンプトがコードに直書きされている** | `agent_invitro/src/` の `generate.py`・`condense.py`・`summarize.py`・`clarify.py`・`llm_tasks/assess/prompts.py`・`graph/agent.py` に `SYSTEM_PROMPT` 定数として散らばっている。プロンプトの差分が他のコード変更に埋もれ、プロンプトの版を単独で示せない |
| 4 | **人手評価の理由が残らない** | `message.evaluation` は 0=未評価 / 1=👍 / 2=👎 の値だけで、なぜ悪いかを書く欄がない（検証機能の `verification_run` には `evaluation_comment` がある） |
| 5 | **回答そのものを自動評価する仕組みがない** | 検証機能（ADR-0049）の対象は tag_selector→knowledge_mcp の検索までで、回答文は評価しない。`web_backend/src/main/evaluate.py`（MRR/TNR）も検索の指標だけで、ローカル実行が前提 |
| 6 | **結果をリポジトリへ持ち帰る経路がない** | 評価済みメッセージは管理画面で見るだけ。改善の判断（仮説・変更・結果）を残す場所もない |

なお、会話はユーザーが評価ボタンを押したときにだけ conversation DB に保存される（`/api/evaluate_response` → `upsert`）。本ADRはこの保存契機を変えない。

## 決定

**回答ごとに「リリース」（コード・プロンプト・モデル・設定の組）と「ナレッジのリビジョン」を記録し、人手評価には理由を残せるようにする。そのうえで、回答まで含めたゴールデンセット評価をローカルの評価ランナーで AWS 検証環境に対して実行し、人手評価とあわせて結果をリポジトリ（`evals/`）に取り込む。改善の判断は `docs/improvements/` に記録する。**

### 1. リリース（回答を生成した構成の版）

リリースは、agent_invitro が回答を生成したときの構成を表す。

| 要素 | 内容 | 取得元 |
|---|---|---|
| `git_commit` / `git_dirty` | コード（プロンプトを含む）の版と、未コミット変更の有無 | デプロイ時に deploy が `GIT_COMMIT` / `GIT_DIRTY` 環境変数とイメージラベルで渡す（ADR-0097 の db_init と同じ方式を agent_invitro に広げる） |
| `prompt_hash` | プロンプトファイル一式の内容ハッシュ（§3） | agent_invitro が起動時に計算する |
| `chat_model_id` / `embedding_model_id` | Bedrock のモデル ID | 既存の環境変数 |
| `params` | 回答に効く設定値（temperature、top_k、Agentic の探索回数など）を JSON にしたもの | agent_invitro の設定 |

- `release_id` は、上の要素を正規化した JSON の SHA-256 の先頭16桁とする。同じ構成なら同じ ID になるので、再デプロイや再起動では増えない。
- agent_invitro は `GET /release` でリリースの全要素を返し、assistant メッセージに `release_id` と `ask_mode`（`pipeline` / `agentic`）を付けて返す。
- web_backend は会話を保存するとき、未登録の `release_id` であれば agent_invitro の `GET /release` で内容を取得して `release` テーブルに登録する。agent_invitro に conversation DB への接続を持たせない（ADR-0045 の責務分担を維持する）。

### 2. ナレッジのリビジョン（回答時点のナレッジ DB の状態）

- ナレッジ DB に `knowledge_revision` テーブルを新設する。検索対象に効くテーブル（`hiroba_qa_original`・`hiroba_question_altered`・`hiroba_category`・`hiroba_qa_tag`・`tag`・`tag_alias`・`tag_folder`・`troubleshooting_article`・`troubleshooting_article_tag`）への INSERT・UPDATE・DELETE・TRUNCATE ごとに、**文単位のトリガー**で1行追加する。
  - 列: `revision`（連番）、`changed_at`、`table_name`、`operation`、`source`（`seed` / `import` / `admin` など。db_init のシード・インポート時はセッション変数で明示し、それ以外は `admin`）。
- 現在のリビジョンは `max(revision)`。knowledge_mcp は `search_knowledge` の結果にこの値を含めて返し、agent_invitro は assistant メッセージに `kb_revision` として付ける。
- リビジョンは「回答時点から後に DB が変わったかどうか」を判定するための番号であって、それだけで中身を復元することはできない。中身を残すため、次の **ナレッジのスナップショット**を設ける。
  - 全データエクスポート（ADR-0047）の SQL ダンプを `snapshots/knowledge/` に置き、DVC で管理する（ADR-0097 で持ち越した「管理画面での編集結果を DVC で管理するか」に、ここで管理すると答える）。
  - スナップショットには取得時点の `kb_revision` を記録する（`snapshots/knowledge/manifest.json`）。
  - 取得は評価ランナーの `snapshot` コマンド（§5）で行い、ゴールデンセット評価の実行前には自動で取る。

### 3. プロンプトのファイル化

- `SYSTEM_PROMPT` 定数を `agent_invitro/prompts/<用途>.md`（`generate.md`・`condense.md`・`summarize.md`・`clarify.md`・`assess.md`・`react_agent.md`）へ移し、起動時に読み込む。
- 文面は変えずに移すだけとし、移した直後の回答は変わらない（移行の前後でテストの期待値が変わらないこと）。
- `prompt_hash` はこのディレクトリの全ファイルの内容から計算する。
- プロンプトの変更は `prompts/` の差分としてレビュー・記録でき、`docs/improvements/` から参照できる。
- Bedrock Prompt Management は使わない。プロンプトをコード・データと同じリポジトリで版管理する方が、このループに合う。

### 4. 人手評価の理由

- conversation DB の `message` に次の列を追加する（yoyo マイグレーション `migrations_conversation/0004`）。
  - `release_id`、`ask_mode`、`kb_revision`：§1・§2
  - `evaluation_comment`、`evaluated_at`：検証機能の `verification_run` と同じ形
- 同じマイグレーションで `release` テーブルを新設する。列は `release_id`（主キー）、§1 の各要素、`first_seen_at`。
- チャット画面の 👎 を押したときに、任意で理由を書ける入力欄を出す。👍 のときも任意で書ける。
- 評価済みメッセージ画面（ADR-0087）に、理由・リリース・`ask_mode` の列と、リリースでの絞り込みを追加する。
- 画面の変更なので、CLAUDE.md の規約に従い、画面遷移図とスクリーンショットも同じ変更の中で更新する。

### 5. 評価ランナー（ローカル → AWS 検証環境）

`evals/` にゴールデンセットと評価ランナーを置く。deploy と同じく Docker コンテナで動かし（ADR-0040）、`terraform/.env` の認証情報と admin_ui の ALB アドレスを使う。呼び出し口は `evals\eval.bat` とする。

| コマンド | 内容 |
|---|---|
| `eval.bat run [--set <名前>] [--mode pipeline\|agentic\|both]` | ゴールデンセットの各質問を admin_ui の `/api/ask-*` に送り、回答・出典・`release_id`・`kb_revision` を記録し、採点する。実行前にナレッジのスナップショットを取る |
| `eval.bat pull-feedback` | `/api/evaluated_messages` から人手評価を取得し、前回からの増分を保存する |
| `eval.bat compare <run A> <run B>` | 2つの実行結果を質問単位で比較し、改善・悪化した質問を一覧にする |
| `eval.bat snapshot` | ナレッジのスナップショットを取り、DVC に追加する（§2） |

**ゴールデンセット**（`evals/golden/<名前>.csv`、git で管理。テキストのみで小さいため DVC は使わない）

- 列: `id`、`question`、`expected_source_ids`（正解の QA・記事 ID、複数可）、`expected_answer_points`（回答に含むべき要点）、`category`、`should_answer`（範囲外の質問は `false`。回答を控えるのが正解）。
- 初版は既存の `data/eval_queries.csv`（質問と正解の QA ID）と `data/eval_noise_queries.csv`（範囲外の質問）から作り、要点を書き足す。
- 人手評価で 👎 になった質問は、内容を確認したうえでゴールデンセットに追加していく（回帰テストとして育てる）。

**採点**（1問ごと）

| 指標 | 方法 |
|---|---|
| 出典の正しさ | `expected_source_ids` が出典に含まれるか、何位か（決定的に計算。既存の MRR と同じ考え方） |
| 回答の正しさ | LLM 採点（Bedrock）。要点の網羅・誤りの有無を 1〜5 で採点し、理由を残す |
| 根拠への忠実さ | LLM 採点。出典に書かれていない内容を断定していないか |
| 回答の控え | `should_answer=false` の質問で、回答を控えたか（決定的に計算 + LLM 採点の併用） |

- 採点に使うモデルは回答用モデルと別に設定できるようにする（`EVAL_JUDGE_MODEL_ID`）。採点プロンプトも `evals/judge_prompts/` に置き、版を記録する。
- LLM 採点は揺れるため、採点の比較は同じ採点モデル・採点プロンプトの実行どうしに限る（結果ファイルに採点側の版も記録する）。

**結果の保存先**（git で管理。テキストのみ）

```
evals/
  golden/<名前>.csv                 ゴールデンセット
  judge_prompts/*.md                採点プロンプト
  runs/<日時>_<release_id>/
    results.jsonl                   1問1行（質問・回答・出典・各スコア・採点理由・release・kb_revision）
    summary.md                      集計と、前回実行との比較（改善・悪化した質問）
    meta.json                       リリースの全要素・kb_revision・スナップショット・採点側の版
  feedback/<日付>.jsonl             人手評価（理由・リリース付き）の増分
```

- 結果がリポジトリに入るので、Claude Code に `evals/runs/` と `evals/feedback/` を読ませて、悪化・低評価の原因分析と、データ・プロンプト・コードの修正案作成を依頼できる。これがループの「持ち帰り」にあたる。
- 実行は都度の手動で行う。定期実行（スケジュール）は、費用と効果を見てから別途判断する。

### 6. 改善の記録

- `docs/improvements/NNNN-<題名>.md` に、1件の改善ごとに次を書く。
  - 仮説（何が悪く、なぜそうなっていると考えたか。根拠にした評価結果・人手評価へのリンク）
  - 変更（コミット、`kb-*` タグ、プロンプトの差分）
  - 結果（変更前後の `evals/runs/` と `compare` の要約）
  - 判断（採用・差し戻し・追加調査）
- 書式は ADR に揃え、テンプレートを `docs/improvements/README.md` に置く。

### 7. 進め方（段階導入）

| 段階 | 内容 | この段階で回るループ |
|---|---|---|
| 1 | §1 リリース記録、§4 の列追加と理由入力、`pull-feedback` | 手動のチャット評価が、理由とリリース付きでリポジトリに戻る |
| 2 | §3 プロンプトのファイル化、§6 改善記録 | プロンプトの変更が単独で追え、改善の過程が残る |
| 3 | §5 ゴールデンセットと `run` / `compare`（出典の正しさと LLM 採点） | 変更前後を同じ質問で定量比較できる |
| 4 | §2 ナレッジのリビジョンとスナップショット | 管理画面での編集も含めて、回答時点のナレッジを特定・再現できる |

各段階で要件定義書・実装計画を起こし、必要に応じて本ADRを改訂する。

**段階①の実装メモ（2026-10-06）**

- `kb_revision` 列は段階④で `knowledge_revision` と一緒に追加する（段階①の `message` には `release_id`・`ask_mode`・`evaluation_comment`・`evaluated_at` のみ）。
- `prompt_hash` は、§3 のファイル化までは回答経路のプロンプト定数（generate・condense・summarize・clarify・assess）の内容から計算する。
- リリースの登録は、評価時ではなく **`/api/ask-*` の中継で回答を受け取った直後**に行う。評価までの間に再デプロイされると、agent_invitro の `GET /release` が別の構成を返しうるため。回答の `release_id` と現在のリリースが一致しない場合は登録しない（誤った内容を記録しない）。
- `git_dirty` は追跡済みファイルの未コミット変更の有無とする（未追跡の作業ファイルは版に影響しないため対象外）。
- `pull-feedback` は1件ごとに「会話・順序・評価・理由・評価日時」から作るキーで重複を除く。評価や理由を付け直したものは新しい行として残る。

## 検討した代替案

- **検証機能（ADR-0048〜0050）を拡張して、回答生成と採点まで画面から行う**
  - 既存の画面・実行履歴の仕組みを流用でき、管理画面だけで完結する。
  - 一方で、ADR-0049 で検索に絞った範囲を大きく広げることになり、画面・API・テーブルの変更が大きい。結果は conversation DB に入るので、リポジトリへ持ち帰るには別の取り出し手段も要る。
  - 検証機能は検索の確認用として残し、回答までの評価はリポジトリに結果が直接残る評価ランナーで行う。不採用。
- **Amazon Bedrock の評価機能（Model evaluation / RAG evaluation）を使う**
  - 採点の仕組みを自前で持たずに済む。
  - 一方で、Bedrock Knowledge Bases を前提とする機能が多く、本システムの独自検索（tag_selector + knowledge_mcp）や `/ask-agentic` の流れにそのまま載らない。結果も AWS 側に残るため、リポジトリへの持ち帰りが別途必要になる。
  - 採点プロンプトとモデルを自分で管理する方が、比較の再現性を保ちやすい。不採用。将来、外部の評価基盤を使う場合も、`results.jsonl` を入力にすれば移行できる。
- **リリースの記録をデプロイ単位（deploy が DB に書く）にする**
  - 仕組みは単純になる。
  - 一方で、ローカル実行や設定だけを変えた再起動を区別できず、「回答がどの構成から出たか」を回答単位で保証できない。不採用。
- **ナレッジの状態を回答時に内容ハッシュで計算する**
  - スナップショットなしで、内容の一致を厳密に判定できる。
  - 一方で、回答のたびに全テーブルを読むことになり、遅延と負荷が見合わない。文単位トリガーの連番とスナップショットの組み合わせを採用する。
- **すべての会話を保存する（評価ボタンを押していないものも含む）**
  - 分析の母数が増える。
  - 一方で、保存契機の変更は利用者のデータの扱いに関わる判断であり、本ADRの範囲（評価結果の持ち帰り）を超える。今回は変えず、必要になったら別ADRで扱う。

## 結果・影響

- 回答・人手評価・自動評価のすべてが `release_id` と `kb_revision` を持つ。「どの変更で良くなった・悪くなったか」を、コード・プロンプト・データ・モデルの単位で追える。
- 評価結果と人手評価がリポジトリ（`evals/`）に入り、Claude Code で原因分析と修正案の作成を続けて行える。改善の判断は `docs/improvements/` に残る。
- **変更が及ぶ範囲**
  - agent_invitro: プロンプトの読み込み、`GET /release`、assistant メッセージへの `release_id`・`ask_mode`・`kb_revision` の付与
  - knowledge_mcp: `search_knowledge` の結果に `kb_revision` を含める
  - web_backend: `release` の登録、`message` の新しい列の保存、評価理由の受け付け、評価済みメッセージ API の拡張
  - front_dev: 評価理由の入力、評価済みメッセージ画面の列・絞り込み（画面遷移図・スクリーンショットの更新を含む）
  - db_init: conversation DB のマイグレーション 0004、ナレッジ DB の `knowledge_revision` とトリガー
  - deploy: agent_invitro イメージへの `GIT_COMMIT` / `GIT_DIRTY` の付与
  - 新規: `evals/`（評価ランナー・ゴールデンセット・採点プロンプト・結果）、`snapshots/knowledge/`（DVC）、`docs/improvements/`
- **費用**: ゴールデンセット評価は1問あたり、回答生成と LLM 採点の Bedrock 呼び出しが発生する。初版のゴールデンセットは数十問規模とし、手動実行に限る。
- **全データエクスポート・インポート（ADR-0047 / ADR-0066）への影響**: conversation DB に `release` テーブルと `message` の列が増える。エクスポート対象のテーブル定義（`web_backend/src/export/tables.py`）とインポートのテーブル一覧（`db_init/src/import_data.py`）を揃えて更新する。`knowledge_revision` はエクスポート対象に含めない（インポート時は `source=import` として新たに記録される）。
- **保存契機が評価時のままである制約**: 評価されなかった会話のリリース情報は残らない。分析の母数は人手評価された会話とゴールデンセットに限られる。
