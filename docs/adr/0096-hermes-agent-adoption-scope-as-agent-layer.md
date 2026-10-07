# ADR-0096: Hermes Agent の導入範囲 — agent_invitro のエージェント層に限定し、/ask-hermes として既存方式と併存させる

- ステータス: Proposed（草案）
- 日付: 2026-10-02
- 関連: ADR-0013（管理UIの書き込み経路をKnowledge MCP経由に統一）、ADR-0019〜0022（agent_invitroの実験構成・ReAct方式）、ADR-0023（AWS内部限定のアクセス範囲）、ADR-0043（agent_invitroの常駐HTTPサービス化）、ADR-0045（資格情報スコープ）、ADR-0052（DBロール分離）、ADR-0065/0066（全データエクスポート・インポート）、ADR-0085（Query Condensation）、ADR-0086（Alias確定タグの決定論的採用）、ADR-0088（Agentic回答生成）、ADR-0089（/ask-agenticの併存とAPI契約の同一性）、ADR-0090（ルーター/ユースケース分離）、ADR-0095（常駐4サービスの1タスク集約）

## コンテキスト

ブランチ `feature/hermesization` では、バックエンドと MCP サーバーとして動いている部分を Nous Research の **Hermes Agent**（MIT License、Python製）に置き換えることを検討している。Hermes Agent は次の機能を持つ汎用の自律エージェントである。

- OpenAI 互換の HTTP API サーバー（`/v1/chat/completions`、`/v1/responses`、`/v1/runs`。SSE ストリーミングに対応）
- 外部 MCP サーバーへの接続（Streamable HTTP / SSE / stdio。`tools.include` / `tools.exclude` でツールを絞れる）
- `SKILL.md` 形式のスキルと、ファイルベースのメモリ。どちらもエージェントが自分で作成・更新する
- 20 以上のメッセージング基盤への gateway（Slack、Microsoft Teams、LINE、Webhook など）
- 組み込みの cron スケジューラ
- 多数の LLM プロバイダ（LM Studio と AWS Bedrock を含む）

現在の構成は次のとおりである。

| コンポーネント | 責務 |
|---|---|
| `web_backend`（admin_ui） | 管理UIの CRUD API（QA・タグ・タグフォルダ・言い換え質問文・トラブルシューティング記事）、評価・検証、会話DB（`conversation` / `message` / `verification_*`）、全データエクスポート、`/api/ask-*` の中継 |
| `agent_invitro` | LangGraph による回答生成。`/ask-pipeline`（単発）と `/ask-agentic`（condense → select_tags → search ⇄ assess を最大2周 → generate / clarify） |
| `knowledge_mcp` | `search_knowledge`（埋め込み類似度、タグ祖先展開、タグ構成類似度スコアリング）と、管理系の約40ツール（CRUD・インポート・エクスポート） |
| `tag_selector_mcp` | `select_tags`（Alias 確定タグの決定論的採用を含む）、`list_taxonomy`、`reload_taxonomy` |

置き換えの範囲を決めるにあたり、次の点が論点になる。

1. **MCP サーバーを Hermes で置き換えられるか**
   - Hermes の MCP サーバーモード（`hermes mcp serve`）は stdio 専用である。
   - 公開されるのはメッセージ送受信・承認用の10ツールだけで、ドメインのツールを載せる仕組みではない。
   - `knowledge_mcp` / `tag_selector_mcp` のロジック（pgvector 検索、スコアリング、タグ階層、DBロール分離）は、Hermes にとっては「接続して使うツール」であって、Hermes の中に移せる性質のものではない。
2. **決定論的なフロー制御を維持できるか**
   - 次の制御は LangGraph のグラフ構造で保証している。
     - condense と select_tags を1回だけ実行する（ADR-0085 / ADR-0086）
     - 探索は最大2周（ADR-0088）
     - 失敗時は pipeline 相当に縮退する（ADR-0088 決定7）
   - Hermes は ReAct 型で、固定のワークフロー／グラフを定義するエンジンを持たない。手順はシステムプロンプトとスキルで誘導するだけになる。
3. **API 契約**
   - `/api/ask-*` は `Request{conversation_id, text, messages, summary}` → `Response{conversation_id, messages, summary}` で同一契約を保っている（ADR-0089 決定2・3）。
   - `user` メッセージの `content` に検索結果（`参考情報:`）を埋め込む形式は、会話評価機能の前提になっている。
   - Hermes はチャット形式のテキストを返すため、変換層が必要になる。
4. **マルチユーザー・状態管理**
   - Hermes のメモリ・スキル・セッション履歴は「プロファイル（HERMES_HOME）」単位で、エンドユーザー単位ではない。
   - エージェントが自分でメモリやスキルを書き換えるので、本番の利用者間で情報が漏れたり、振る舞いが予告なく変わったりするおそれがある。
   - 同じ HERMES_HOME に複数のプロセスから書き込むことは非推奨とされており、水平スケールしにくい。
5. **攻撃面**
   - Hermes にはターミナル・ファイル操作・コード実行などの組み込みツールがある。
   - API サーバーはベアラーキー1本でツール一式に到達できる設計である。
6. **小規模ローカルモデルとの相性**
   - ローカルの既定モデル（`google/gemma-4-e4b`）が、Hermes のシステムプロンプトとツール定義の大きさに耐えられるかは確かめていない。

## 決定

**Hermes Agent は `agent_invitro` のエージェント層（回答生成のオーケストレーション）の代替候補としてだけ導入し、`/ask-hermes` という第3の方式として既存の `/ask-pipeline`・`/ask-agentic` と併存させる。`knowledge_mcp`・`tag_selector_mcp`・`web_backend` の管理・評価・会話DBの責務は置き換えない。** 本ADRの範囲は PoC（比較評価）までとし、本採用と既存方式の廃止は評価結果を見て別ADRで判断する。

### 1. 置き換えの範囲

| コンポーネント | 扱い |
|---|---|
| `knowledge_mcp` / `tag_selector_mcp` | **変更しない。** Hermes からは MCP クライアントとして Streamable HTTP（`/mcp`）で接続する。 |
| `web_backend` | 管理 CRUD・評価・検証・会話DB・エクスポートは**変更しない**。`/api/ask-hermes` を新設し、Hermes への中継と契約の変換（決定3）を担う BFF とする。 |
| `agent_invitro` | **併存させる。** `/ask-pipeline`・`/ask-agentic` は残し、比較対象にする。 |
| Hermes Agent | 新規コンテナ `hermes_agent` として追加する。gateway プロセスの API サーバーだけを有効にする。 |

```
front_dev ─▶ web_backend
               ├ /api/ask-pipeline ─┐
               ├ /api/ask-agentic  ─┴▶ agent_invitro (LangGraph) ─┐
               └ /api/ask-hermes   ──▶ hermes_agent (API server) ─┤ MCP (streamable HTTP)
                                                                 ├▶ tag_selector_mcp
                                                                 └▶ knowledge_mcp
```

### 2. ツールの公開範囲（読み取り系のみ）

Hermes の `mcp_servers` 設定で `tools.include` を使い、回答生成に必要な読み取り系ツールだけを公開する。管理系の CRUD・インポート・エクスポートは公開しない（ADR-0013 の「書き込みは管理UI経由」を維持する）。

```yaml
mcp_servers:
  knowledge:
    url: http://knowledge_mcp:8100/mcp
    tools:
      include: [search_knowledge, get_qa, list_categories]
      resources: false
      prompts: false
  tag_selector:
    url: http://tag_selector_mcp:8200/mcp
    tools:
      include: [select_tags, list_taxonomy]
      resources: false
      prompts: false
```

- Hermes の組み込みツールのうち、ターミナル、ファイル操作、コード実行、Web 検索、cron 管理、サブエージェント委譲、Kanban は**すべて無効**にする。
- `approvals.unattended_mode` は既定の `deny` のままにする。

### 3. API 契約は既存と同一にし、変換は web_backend が担う

- `/api/ask-hermes` のリクエスト・レスポンスは、`/api/ask-pipeline`・`/api/ask-agentic` と同じスキーマ（`chat_schemas.py`）を使う（ADR-0089 決定2 を踏襲）。
- `web_backend` は会話履歴（`messages`・`summary`）を Hermes の `messages` 配列に変換して送る。Hermes 側のセッション（`X-Hermes-Session-Id`）は**使わない**。会話の正本は引き続き `conversation` データベースとし、Hermes は1リクエストごとにステートレスに扱う。
- 応答の `user` メッセージに入れる `参考情報:` には、Hermes が実行した `search_knowledge` の結果を入れる。取得経路の第一候補は Responses API の `function_call_output` アイテムとし、取得できるかどうかを PoC で確認する。取得できない場合は、`assistant` の回答だけを返し `参考情報` は空にする制約付きの運用とし、評価での扱いを別途決める。
- `assistant` メッセージの `model` には Hermes が使ったモデル ID を入れ、`input` にはシステムプロンプトとスキルの識別子を記録する。
- 探索の経過（ツール呼び出しの順序・引数・件数）は、ADR-0089 決定4 と同じく `logger.info` でだけ出力する。

### 4. 回答手順はスキルで定義し、自己改変は禁止する

- 「社内QA回答手順」スキル（`SKILL.md`）を作り、リポジトリで管理する。ADR-0088 のフロー（言い換え → タグ選定 → 検索 → 十分性の判断 → 再検索は最大1回 → 回答、または逆質問）を自然言語で記述する。根拠が見つからない場合に推測で回答しないことも明記する。
- スキルはコンテナイメージに読み取り専用で同梱する。`skills.write_approval: true` を設定したうえで、`skill_manage` ツールを無効にする。
- メモリ（`MEMORY.md` / `USER.md`）の書き込みと、外部メモリプロバイダは**使わない**。利用者間の情報漏えいと、承認されていない振る舞いの変化を防ぐためである。Hermes の売りである「自己改善」は、本ADRの範囲では意図的に使わない。

### 5. LLM プロバイダは既存方式と揃える

- ローカルは `provider: lmstudio`、AWS は `provider: bedrock`（IAM タスクロールの認証情報、Converse API）とし、`agent_invitro` と同じモデル ID を使う。比較評価の条件を揃えるためである。
- ローカルの小規模モデルでツール選択が安定しない場合は、ローカルでの評価を参考扱いにし、Bedrock 上での比較を判断材料にする。

### 6. 実行形態

- **ローカル（docker-compose）**
  - サービス `hermes_agent` を追加し、API サーバー（既定ポート 8642）をコンテナ内ネットワークだけに公開する。
  - `API_SERVER_KEY` は `.env` で指定する。
- **AWS**
  - ADR-0095 の集約タスクに、5つ目のコンテナとして追加する。
  - ALB からの到達性は与えず、`admin_ui` からのタスク内通信だけを受ける（ADR-0023 / ADR-0043 を踏襲）。
  - `API_SERVER_KEY` は Secrets Manager から注入する。Bedrock 呼び出し権限は Hermes コンテナ用の範囲に限定する（ADR-0045）。
- **HERMES_HOME の扱い**
  - 永続ボリュームを使わない（エフェメラル）。
  - 設定とスキルはイメージに同梱する。`state.db`（セッション履歴）はタスクの再起動で消えてよい。会話の正本は `conversation` データベースにあるためである（決定3）。
  - この前提のため、EFS は不要とする。
- Hermes の導入手段（pip / 公式インストーラ）とバージョン固定の方法は PoC で確定する。

### 7. 評価と判断基準

- フロントエンドの方式トグル（ADR-0089 決定5）に「Hermes 方式」を追加し、同じ質問を3方式で比較できるようにする。
- 既存の評価機能・検証機能（`verification_*`）を使い、次の項目を `/ask-agentic` と比べる。
  - 正答 QA の検索ヒット率
  - 回答の評価値
  - レイテンシ（p50 / p95）
  - Bedrock の呼び出し回数とコスト
  - 「推測で回答しない」制約の遵守率
- ReAct のため手順の順守は保証されない。そこで、ログから「select_tags を呼ばなかった」「3回以上検索した」などの逸脱率も測る。
- 本採用・不採用・用途を変えて採用する（決定8）のいずれにするかは、上の結果をもとに別ADRで決める。

### 8. 範囲外（将来検討）

次の用途は Hermes の強みが活きるが、本ADRでは扱わない。

- Slack / Teams などの gateway による社内チャネル窓口
- cron による定期検証やレポート配信
- 自然言語による管理操作アシスタント（管理系 MCP ツールを `trust: untrusted` で承認必須にした別プロファイルを用意する案）

## 検討した代替案

- **web_backend・agent_invitro・MCP サーバーをすべて Hermes に置き換える**
  - 構成要素が減り、Hermes のスキルとツールに集約できる利点がある。
  - しかし Hermes の MCP サーバーモードではドメインのツールを公開できない。管理UIの CRUD、評価・検証、会話DB、DBロール分離、全データエクスポート／インポートの受け皿もない。
  - 検索ロジックをスキル付属のスクリプトに移すと、テスト済みの `knowledge_mcp`（祖先展開・スコアリング）を作り直すことになる。
  - 以上の理由で不採用とした。

- **agent_invitro を Hermes で即時に置き換える（併存させない）**
  - 運用するコンポーネントが増えない。
  - しかし決定論的なフロー制御を失ううえ、精度とレイテンシを確かめていない段階で切り戻し手段がなくなる。ADR-0089 で `/ask-agentic` を併存させたのと同じ理由で不採用とした。

- **Hermes を Python ライブラリ（`AIAgent`）として agent_invitro に組み込む**
  - コンテナとポートが増えない。
  - しかし LangGraph と Hermes の2つのエージェント実行基盤が同じプロセスに同居し、依存関係とプロセスの状態（HERMES_HOME）の管理が複雑になる。API サーバーとして分けておけば、不採用になったときにコンテナを外すだけで済む。
  - PoC の段階では分離しやすさを優先し、不採用とした。

- **Hermes のセッション機能（`X-Hermes-Session-Id` / Responses の `conversation`）を会話の正本にする**
  - `web_backend` が履歴を送らずに済む。
  - しかし会話の保存先が `state.db`（SQLite）と `conversation` データベースに分かれ、会話評価機能や全データエクスポート（ADR-0065/0066）の対象から外れる。HERMES_HOME を永続化する必要も出てくる。
  - 以上の理由で不採用とした。

- **Hermes のメモリとスキルの自己改善を有効にする**
  - Hermes の主要な特長で、利用するほど回答手順が洗練される可能性がある。
  - しかしメモリとスキルはプロファイル単位で全利用者に共有される。ある利用者の情報が他の利用者への回答に混入するおそれがあり、レビューされていない手順の変更が本番の挙動を変えてしまう。
  - 社内QAボットとしての説明責任と再現性を優先して不採用とした。スキルの改善は、人がレビューしてリポジトリにコミットする運用にする。

- **利用者ごとに Hermes プロファイルを分ける**
  - メモリを利用者ごとに分けられる。
  - しかしプロファイルごとにプロセス・ポート・キーが必要で、ECS の1タスク構成（ADR-0095）とコスト削減方針に反する。メモリを使わない方針（決定4）であれば、分ける必要もない。
  - 以上の理由で不採用とした。

## 結果・影響

- **新規**
  - `hermes_agent/`：Dockerfile、`config.yaml`、`skills/社内QA回答手順/SKILL.md`。
  - `web_backend`：`agent_controller.ask_hermes()`、`POST /api/ask-hermes`、Hermes 応答から既存スキーマへの変換処理、環境変数 `HERMES_API_BASE_URL` / `HERMES_API_KEY` / `HERMES_TIMEOUT`。
- **front_dev**
  - `domain/stateless/ask_mode.ts` に方式 `hermes` を追加し、ヘッダーのトグルを3択にする。
  - これは画面内の主要な操作の変更にあたるため、実装時には CLAUDE.md の規約に従い、`docs/screen_transition/画面遷移図.md` の説明文とチャット画面のスクリーンショットを同じコミットで更新する。
- **Terraform**
  - ADR-0095 の集約タスク定義に `hermes_agent` コンテナを追加する。
  - Secrets Manager に `API_SERVER_KEY` を追加する。
  - Bedrock 呼び出し権限を付与する。
  - タスクサイズ（CPU / メモリ）を見直す必要が出る可能性がある。
- **変更しないもの**
  - `knowledge_mcp` / `tag_selector_mcp` と DB スキーマ。
  - 会話評価データ（`conversation` データベース）は方式を区別しない、という既存の制約（ADR-0089 結果・影響）が、3方式に広がった形で残る。比較評価を集計するなら、方式列の追加（ADR-0044 の見直し）を本ADRの PoC と併せて検討する。
- **リスク**
  - ReAct 型のため、手順の順守・応答時間・Bedrock の呼び出し回数がばらつく。
  - Hermes 本体の更新頻度が高い場合、バージョン固定と追随のコストがかかる。
  - 公式ドキュメントの記述には揺れがあり（例：MCP ツール名の区切りが `mcp_<server>_<tool>` か `mcp__<server>__<tool>` か）、仕様は PoC で実際に動かして確認する。
- **PoC で確認すること（未確定事項）**
  1. Responses API で `search_knowledge` の結果（`function_call_output`）を取り出し、`参考情報` を組み立てられるか（決定3）。
  2. 組み込みツールを完全に無効化する設定方法と、それが効いていることの確認手段（決定2）。
  3. ローカルモデル（gemma-4-e4b）でツール選択が安定するか（決定5）。
  4. Hermes の導入手段とバージョン固定の方法（決定6）。
  5. 同時実行の上限（既定10）と、ECS タスクサイズとの関係。

## 参考

- Hermes Agent ドキュメント: https://hermes-agent.nousresearch.com/docs
- API Server: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
- MCP: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp ／ https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference
- Providers: https://hermes-agent.nousresearch.com/docs/integrations/providers
- Memory ／ Skills: https://hermes-agent.nousresearch.com/docs/user-guide/features/memory ／ https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
- Security: https://hermes-agent.nousresearch.com/docs/user-guide/security
- Profiles: https://hermes-agent.nousresearch.com/docs/user-guide/profiles
