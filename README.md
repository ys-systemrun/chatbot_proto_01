### 利用前に
1. LMStudio を立ち上げて chat用モデルとembedding用モデルをダウンロードしてください。.env.exampleでは仮に google_gemma-4-E4B-it-GGUF(google/gemma-4-e4b), Nomic-embed-text-v1.5-Embedding-GGUF(text-embedding-nomic-embed-text-v1.5@q8_0) をダウンロードするものとします。その後、Ctrl + 2 でDevelopper画面に移動し、上部のトグルで LM Studio Local Serve を Running にし、Load Model ボタンでダウンロードした2つのモデルをロードしてください。
2. .env.example を コピーして .env にリネームし、モデル名含む環境依存の各種パラメータを入力してください。`DB_DIR` に対応した `EMBEDDING_VECTOR_DIM`（`db_nomic` なら 768、`db_multilingual` なら 384）を必ず設定してください。
3. `docker compose up` を実行してください。スキーマ作成（マイグレーション）と初期データ投入（シード、embedding計算を含む）は、専用のワンショットサービス `db_hiroba_qa_init` が自動的に実行します（IMPL-202608061016 / ADR-0016〜0018）。手動でのシーディング操作は不要です。既存データが投入済みの場合は、テーブル単位の存在チェックにより自動的にスキップされます。

> **注意**: シードは `question_altered` の各行について LM Studio の embedding エンドポイントを呼び出します。`docker compose up` の前に LM Studio を起動し、embedding 用モデルをロードしておいてください。未起動のままだと `db_hiroba_qa_init` がシードに失敗し（非0終了）、これに依存する `web_backend` / `knowledge_mcp` / `tag_selector_mcp` は起動しません。ログは `docker compose logs db_hiroba_qa_init` で確認できます。

#### 既存環境（手動 migration 適用済みボリューム）からの移行

既に旧方式（`db_nomic/init.sql` ＋ `knowledge_mcp/migrations/` 等の手動適用）でスキーマを構築済みの既存 `db_nomic/data` を使う場合、`db_hiroba_qa_init` の全マイグレーションSQLは `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` でガードされているため、**そのまま `docker compose up` しても既存テーブル・列に対して無害に完了します**（未追跡のマイグレーションを yoyo が再実行しても、実体は作成済みのためスキップと同義）。

マイグレーションを「適用済み」として yoyo の追跡テーブルに明示登録（ベースライン化）したい場合は、`yoyo mark` を利用できます。

```bash
# 実行前に LM Studio 等は不要（マイグレーション履歴の登録のみ）。既存の全ステップを適用済みとして記録する。
docker compose run --rm db_hiroba_qa_init \
  yoyo mark --batch --database "postgresql://postgres:postgres@db_hiroba_qa:5432/chatbot" ./migrations
```

#### DBロール分離に伴う接続情報の変更点（IMPL-202608261022 / ADR-0052）

`chatbot` / `conversation` の両データベースは、用途別ロール（`migrator` / `app`）に分離されました。開発者は今後、単一の `postgres` マスターユーザーではなく、`chatbot_app` / `chatbot_migrator`（および `conversation_app` / `conversation_migrator`）の資格情報を意識する必要があります。

- アプリケーション（`web_backend` / `knowledge_mcp` / `tag_selector_mcp`）は `chatbot_app` ロールで `chatbot` DB に接続します。`web_backend` の会話DBは `conversation_app` ロールで接続します。`app` ロールは DML（SELECT/INSERT/UPDATE/DELETE）権限のみを持ち、DDL 権限を持ちません。
- ロールの作成・スキーマのマイグレーションを行うのは `db_hiroba_qa_init` サービスのみです（`migrator` ／マスター権限で実行）。

ローカルの `docker compose` 環境では、各ロールのパスワードを `.env` で固定値指定できます（未指定時は下表の既定値が使われます）。AWS 環境では Terraform / Secrets Manager から注入されます。

| 環境変数 | 対象ロール | 既定値 |
|---|---|---|
| `CHATBOT_MIGRATOR_PASSWORD` | `chatbot_migrator` | `chatbot_migrator_pw` |
| `CHATBOT_APP_PASSWORD` | `chatbot_app` | `chatbot_app_pw` |
| `CONVERSATION_MIGRATOR_PASSWORD` | `conversation_migrator` | `conversation_migrator_pw` |
| `CONVERSATION_APP_PASSWORD` | `conversation_app` | `conversation_app_pw` |

#### conversation データベースのベースライン化（IMPL-202608261022 / ADR-0051）

本実装で、`conversation` データベースのスキーマ適用が `init.sql` の直書きから yoyo マイグレーション（`db_hiroba_qa_init/migrations_conversation/`）へ移行しました。既存ボリューム（`conversation` / `message` の2テーブル、検証機能実装後は `verification_*` 系4テーブルも含む計6テーブルが既に存在する環境）を使う場合は、上の `chatbot` 向け `yoyo mark` と同様に、`conversation` データベース側も既存テーブルを「適用済み」として yoyo の追跡テーブルに登録します。

```bash
# conversation データベースの既存テーブルを適用済みとしてyoyoの追跡テーブルに登録する
yoyo mark --batch --database "postgresql://conversation_migrator:<password>@localhost:5433/conversation" ./db_hiroba_qa_init/migrations_conversation
```

> ローカルの `conversation_db` は既定でホスト `5433` ポート（`.env` の `CONVERSATION_DB_PORT` で変更可）。コンテナ間で実行する場合はホスト名・ポートを `conversation_db:5432` に読み替えてください。`<password>` は `CONVERSATION_MIGRATOR_PASSWORD`（既定 `conversation_migrator_pw`）を指定します。

#### .env 設定項目

| 項目 | 値の例 | 説明 | 
|---|---|---|
| BOT_PORT | 8000 | FastAPI がリクエストを受け付けるポート |
| FRONT_PORT | 5173 | デバッグ UI (Vite dev server) の対ホストポート |
| DB_PORT | 5432 | Q&Aおよび埋め込みベクトルデータを保存するPostgreSQL DBコンテナの対ホストポート |
| DB_DIR | db_nomic | DBとして使うディレクトリ。 ./{DB_DIR}/data 下には PostgreSQL のデータクラスタが構築される（永続化ボリューム）。 |
| EMBEDDING_VECTOR_DIM | 768 | `db_hiroba_qa_init` が `question_altered.embedding` を `VECTOR(N)` で作成する際の次元数。`DB_DIR` に対応させる（`db_nomic`→768, `db_multilingual`→384）。埋め込みモデル差異はこの1変数で吸収し、スキーマは単一のマイグレーション履歴で管理する（ADR-0017）。 |
| CSV_DATA_DIR | data | 読み込むデータ内容を記述したCSVファイルやJSONファイルを配置したディレクトリ。 |
| QA_ORIGINAL_FILE | exportjson_withguid_small.json | オリジナルの質問・回答の組データのJSONファイル。(GUIDを付与したもの) |
| QUESTION_ALTERED_FILE | question_altered_small.csv | オリジナルと同様のことを違う聞き方で聞いた場合のパターン群。ChatGPTにより生成。 |
| CATEGORY_FILE | category.csv | 問い合わせを分類するカテゴリとそのコード値を記載したファイル。 |
| MODEL_EMBEDDING | text-embedding-nomic-embed-text-v1.5@q8_0 | embedding用のモデル名 |
| LMSTUDIO_EMBDDING_URL | http://host.docker.internal:1234/v1/embeddings | LM Studio 上の embedding用のモデルのエンドポイント |
| MODEL_CHAT | google/gemma-4-e4b | チャット作成用のモデル名 |
| LMSTUDIO_CHAT_URL | http://host.docker.internal:1234/v1/chat/completions | LM Studio 上の チャット作成用のモデルのエンドポイント |
| EVAL_QUERIES_CSV | eval_queries.csv | 評価用のクエリ:正解の qa_id の組 |

## 全データインポート（別環境への投入 / 同一環境への再投入）

全データエクスポート機能で取得した `chatbot.sql` / `conversation.sql` を別環境へ投入する運用手順です。AWS 環境では **バッチ自動実行（`import-data.bat`, ADR-0066）を第一手段**とし、手動の ECS Exec 手順（ADR-0055）はバッチが失敗したときの障害切り分け・手動リカバリ手段として併存させます。

> **前提**（ADR-0066 で更新）:
> - 既存データがある環境にも投入できます（**全消去→上書き**方式）。バッチ方式は全消去の直前に既存データを **自動でバックアップ**（S3 の `rollback/` プレフィックス）してから実行します。
> - エクスポート元と投入先が **同一のマイグレーション適用状態（スキーマバージョン）** であることを前提とします（テーブル定義は作り変えません。スキーマ差異がある場合は対象外, ADR-0066 §4）。
> - 全消去→上書きは不可逆操作のため、バッチ実行時は **対象クラスタ名のタイプ確認** を必須とします（ADR-0066 §6）。
> - 実行中は対象データベースへ直接接続するサービス（`web_backend`(=`admin_ui`)・`knowledge_mcp`・`tag_selector_mcp`）を停止します。バッチ方式はこの停止・再開も内包します（ADR-0066 §8）。
> - ブラウザUIは提供しません。運用者による CLI ／一時タスク実行のみです（発注者確認#6）。
> - 対象テーブルは全データエクスポート機能と同一（`chatbot` 6テーブル・`conversation` 6テーブルの計12テーブル）。バックアップ・全消去・再投入をこの集合で一致させます（ADR-0066 §4）。

### バッチ自動実行（AWS, 推奨 / ADR-0066）

`terraform/import-data.bat` をダブルクリックするだけで、S3 アップロード → サービス停止 → 事前自動バックアップ → 全消去 → 上書き投入 → サービス再開までを 1 回で完結します（ADR-0040 の `.bat` UX を踏襲。中身はコンテナ内 Python オーケストレータ = `deploy import-data`）。

```bat
rem 1. エクスポート成果物を terraform\ 配下に置く（既定のファイル名）
rem      terraform\chatbot.sql
rem      terraform\conversation.sql

rem 2. バッチを実行（ダブルクリック = 両データベース）
terraform\import-data.bat
rem   一方のみ: terraform\import-data.bat --target chatbot
rem            terraform\import-data.bat --target conversation
rem   別パス指定: terraform\import-data.bat --chatbot-sql path\to\chatbot.sql
```

実行時、対象クラスタ名の入力を求められます（誤操作防止のタイプ確認, §6）。正しく入力すると次を自動実行します。

- 投入ダンプを `s3://<import-bucket>/import/<db>.sql` へアップロード（§7）
- 対象サービスを `desired_count=0` に変更しタスク停止を待機（停止前の値を記録, §8）
- `db_hiroba_qa_init` を `IMPORT_MODE` で run-task 起動 → `STOPPED` まで待機 → `exitCode=0` を確認（§1）
  - コンテナ内: 消去対象データを `s3://<import-bucket>/rollback/<db>/<時刻>/<db>.sql` へ退避（§5）→ 対象テーブルを `TRUNCATE ... RESTART IDENTITY CASCADE` → 投入ダンプを同一トランザクションで適用（§4）
- 対象サービスを停止前の `desired_count` へ戻し安定化を待機（成功・失敗どちらでも再開, §8）

`<import-bucket>` は `terraform apply`（`apply-database`）が作成する専用バケット（`<name_prefix>-import-<account-id>-<region>`）です。運用者による事前の S3 準備・`aws s3 cp`・サービス停止/再開は不要です。異常終了した場合は、退避バックアップ（`rollback/`）と CloudWatch Logs `/ecs/db-hiroba-qa-init` を確認し、必要に応じて下記の手動手順（ECS Exec）で切り分けます。

> **退避バックアップの運用ルール**（保持期間・世代管理）は別途定めてください（ADR-0066 結果・影響）。バケットはバージョニング有効です。
>
> **実行主体（`terraform/.env` の AWS 認証情報）に必要な権限**: サービス停止・再開のための `ecs:UpdateService` / `ecs:DescribeServices`、投入ダンプアップロードのための import バケットへの `s3:PutObject`、run-task 系（`ecs:RunTask` / `ecs:DescribeTasks`）。`apply-*` を実行できる権限があればおおむね満たされます（ADR-0066 結果・影響）。

### 手動手順（障害時のフォールバック / ADR-0055）

バッチ処理が想定外の状態（S3 上のファイル不備、権限不足等）で失敗した場合の、手動での切り分け・リカバリ手段です。通常運用ではバッチ方式（上記）を使ってください。

#### ローカル環境（docker compose）

```bash
# 1. メンテナンス時間帯を設け、対象サービスを停止する
docker compose stop web_backend knowledge_mcp tag_selector_mcp agent_invitro

# 2. 新規（空の）DBへSQLダンプを投入する（既存データがある状態は非対応）
docker compose exec -T db_hiroba_qa psql -U chatbot_migrator -d chatbot < chatbot.sql
docker compose exec -T conversation_db psql -U conversation_migrator -d conversation < conversation.sql

# 3. サービスを再開する
docker compose start web_backend knowledge_mcp tag_selector_mcp agent_invitro
```

> **PowerShell（Windows）での注意**: PowerShell では `<`（入力リダイレクト）が使えません。手順2は `Get-Content` からのパイプに置き換えてください。CP932 環境での文字化けを避けるため、SQLダンプが UTF-8 の場合は `-Encoding utf8` を明示するのが安全です。
>
> ```powershell
> Get-Content -Encoding utf8 chatbot.sql | docker compose exec -T db_hiroba_qa psql -U chatbot_migrator -d chatbot
> Get-Content -Encoding utf8 conversation.sql | docker compose exec -T conversation_db psql -U conversation_migrator -d conversation
> ```

#### AWS 環境（ECS Exec）

バッチ方式（上記）が失敗したときの手動リカバリ手段です。常駐サービスや ALB エンドポイントを新設せず、既存の `db_hiroba_qa_init` タスク定義を一時的に起動して ECS Exec（`aws ecs execute-command`、ADR-0029 と同様の実行形態）で接続し、コンテナ内から対象 RDS へ `psql` でダンプを投入します（ADR-0055/0066 §2）。SQL ファイルの受け渡しは **S3 経由**で行います。

> **前提（ADR-0066 で反映済み）**: 本手順が使う次の 2 点は、バッチ方式の実装（ADR-0066）と併せて反映済みです。
>
> 1. **`psql` / `aws` CLI の同梱**: `db_hiroba_qa_init/Dockerfile` に `postgresql-client`・`awscli` を同梱済みです（ECS Exec 内で `psql` / `aws s3 cp` が使えます）。
> 2. **S3 権限**: `terraform/modules/db-init-task` の task role に、import バケットへの `s3:GetObject` / `s3:PutObject` / `s3:ListBucket` を付与済みです（`import_bucket_arn` に限定）。
>
> ECS Exec 用の SSM 権限（`ssmmessages:*`）も task role に付与済みです。`run-task` 時に `--enable-execute-command` を付ければそのまま接続できます。`<import-bucket>` は `apply-database` が作成する専用バケット（`<name_prefix>-import-<account-id>-<region>`）です。

以下、コマンド例。プレースホルダ（`<region>` / `<import-bucket>` / `<task-arn>` 等）は各環境の値に読み替えてください。クラスタ名・サブネット・SG・タスクファミリは、シード（`seed.bat`）と同じ Terraform output から取得します。

```bash
# 0. 事前情報の取得（シードと同じ output を流用。terraform/README.md「Phase 4」参照）
#    CLUSTER … app 構成 output（cluster_name）
#    SUBNETS / SG / TD … database 構成 output（private_subnet_ids / sg_verification_task_id / db_init_task_family）

# 1. エクスポート成果物を S3 にアップロード（運用者が用意した投入用バケットへ）
aws s3 cp chatbot.sql      s3://<import-bucket>/import/chatbot.sql      --region <region>
aws s3 cp conversation.sql s3://<import-bucket>/import/conversation.sql --region <region>

# 2. メンテナンス時間帯: 対象サービスを停止する（desired_count=0, 発注者確認#10）
for svc in admin_ui knowledge_mcp tag_selector_mcp agent_invitro; do
  aws ecs update-service --cluster $CLUSTER --service $svc --desired-count 0 --region <region>
done
aws ecs wait services-stable --cluster $CLUSTER \
  --services admin_ui knowledge_mcp tag_selector_mcp agent_invitro --region <region>

# 3. db_hiroba_qa_init タスクを「シード実行させず」一時起動する。
#    既定 CMD（python src/main.py = マイグレーション+シード）を sleep で上書きし、ECS Exec 用に待機させる。
aws ecs run-task --cluster $CLUSTER --launch-type FARGATE \
  --task-definition $TD --enable-execute-command \
  --overrides '{"containerOverrides":[{"name":"db-hiroba-qa-init","command":["sleep","3600"]}]}' \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --region <region>
#   → 起動した <task-arn> を控える（describe-tasks で RUNNING を確認してから次へ）

# 4. ECS Exec でコンテナ内シェルに接続する
aws ecs execute-command --cluster $CLUSTER --task <task-arn> \
  --container db-hiroba-qa-init --command "/bin/sh" --interactive --region <region>
```

コンテナ内シェルに入ったら、S3 からダンプを取得して新規（空の）DB へ投入します。接続情報はタスクへ注入済みの環境変数（`DATABASE_URL` = chatbot、`CONVERSATION_DB_URL` = conversation）を利用します。

```sh
# --- ECS Exec で入ったコンテナ内 ---
aws s3 cp s3://<import-bucket>/import/chatbot.sql      /tmp/chatbot.sql
aws s3 cp s3://<import-bucket>/import/conversation.sql /tmp/conversation.sql

# 既存データがある場合は、投入前に対象テーブルを手動で全消去する（バッチ方式の TRUNCATE 相当）。
#   例（chatbot）: psql "$DATABASE_URL" -c 'TRUNCATE category, qa_original, tag, question_altered, tag_alias, qa_tag RESTART IDENTITY CASCADE;'
#   例（conversation）: psql "$CONVERSATION_DB_URL" -c 'TRUNCATE conversation, message, verification_question, verification_run, verification_run_tag, verification_run_source RESTART IDENTITY CASCADE;'
# 全消去の前に、必要ならエクスポート機能で退避バックアップを取得しておくこと（誤操作時の復旧手段, ADR-0066 §5）。

# ダンプを投入する（空DB へはそのまま、既存データありなら上記 TRUNCATE 後に）
psql "$DATABASE_URL"        -v ON_ERROR_STOP=1 -f /tmp/chatbot.sql
psql "$CONVERSATION_DB_URL" -v ON_ERROR_STOP=1 -f /tmp/conversation.sql
exit
```

投入完了後、一時タスクを停止し、サービスを再開します。

```bash
# 5. 一時タスクを停止する
aws ecs stop-task --cluster $CLUSTER --task <task-arn> --region <region>

# 6. サービスを再開する（desired_count=1）
for svc in admin_ui knowledge_mcp tag_selector_mcp agent_invitro; do
  aws ecs update-service --cluster $CLUSTER --service $svc --desired-count 1 --region <region>
done

# 7. 後始末: S3 に置いた一時ダンプを削除する
aws s3 rm s3://<import-bucket>/import/chatbot.sql      --region <region>
aws s3 rm s3://<import-bucket>/import/conversation.sql --region <region>
```

> **注記**:
> - `desired_count=1` は既定運用の値です。`knowledge_mcp` を複数タスクで運用している場合は元の値に戻してください。`terraform apply`（`apply-app`）で管理している場合は、再開を `terraform apply` に委ねても構いません。
> - `psql` の `-v ON_ERROR_STOP=1` により、途中の SQL エラーで停止します（部分適用の追跡を容易にするため。非機能要件「部分失敗時の扱い（全データインポート）」）。
> - 投入用 S3 バケットは Terraform state バケットとは別に、`apply-database` が専用バケット（`<name_prefix>-import-<account-id>-<region>`）として作成します（ADR-0066）。task role への `s3:GetObject`/`s3:PutObject`/`s3:ListBucket` はこのバケットに限定して付与済みです。`<import-bucket>` にはこの名前を読み替えてください。

## デバッグ UI による動作確認

`front_dev/` に含まれる TypeScript + Vite 製のシンプルな UI を使って、バックエンドの動作をブラウザから確認できます。

### 前提条件

以下がすべて満たされている状態で進めてください。

- LMStudio が起動しており、chat 用・embedding 用の両モデルが **Load** されている
- `.env` を `.env.example` からコピーして編集済みである
- DB のシーディングが完了している（初回のみ。後述「シーディング」参照）

### 起動

プロジェクトルートで以下を実行します。

```bat
REM Windows
build.bat
```

```bash
# Unix / WSL
docker compose up -d --build
```

3 つのコンテナ（`chatbot_db` → `chatbot_app` → `chatbot_frontend`）が順に起動します。  
初回は `npm install` を含むビルドが走るため数分かかります。

起動状況は以下で確認できます。

```bash
docker compose ps
docker compose logs -f frontend   # Vite の起動ログ
docker compose logs -f web_backend        # FastAPI の起動ログ
```

`chatbot_frontend` のログに `Local: http://localhost:5173/` が表示されれば準備完了です。

### ブラウザからアクセス

```
http://localhost:5173
```

ポートを変更した場合は `.env` の `FRONT_PORT` の値に合わせてください。

### 動作確認手順

#### 1. 質問を送信する

テキストエリアに製品に関する質問を入力し、「送信」ボタンまたは **Ctrl+Enter** を押します。

#### 2. Session ID の発行を確認する

初回送信後、ヘッダーの **Session ID** 欄に UUID が表示されます。  
この値がバックエンドで管理されるセッションキーです。

#### 3. アシスタントの回答を確認する

アシスタントのメッセージが表示されます。  
回答の下にある **「API レスポンス (JSON)」** を展開すると、バックエンドからの生レスポンスを確認できます。

```json
{
  "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "answer": "お問い合わせいただきありがとうございます。..."
}
```

#### 4. 会話の継続を確認する

続けて別の質問を送信し、ヘッダーの Session ID が **変わらず同じ値**のままであることを確認します。  
これにより、会話履歴が同じセッションに蓄積されていることが分かります。

#### 5. セッションリセットを確認する

「**セッションリセット**」ボタンを押すと、以下が行われます。

- `DELETE /session/{session_id}` がバックエンドに送信される
- 画面の会話履歴がクリアされる
- Session ID 表示が「（未開始）」に戻る

次の送信で新しい Session ID が発行されれば、リセットが正常に機能しています。

### トラブルシューティング

| 症状 | 確認箇所 |
|---|---|
| `http://localhost:5173` に繋がらない | `docker compose ps` で `chatbot_frontend` が `Up` か確認。`docker compose logs frontend` でエラーを確認 |
| 質問を送ると `502 Bad Gateway` が返る | `chatbot_app` が起動しているか確認。`docker compose logs web_backend` を参照 |
| 回答が返らず長時間待機になる | LMStudio でモデルがロードされているか確認 |
| `Session ID` が毎回変わる | `chatbot_app` が再起動している可能性あり。`InMemorySessionStore` はプロセス再起動でデータが失われる |

---

## 評価 (MRR)

このリポジトリには、データベースの類似検索 `DB.search_similar` の性能指標として MRR (Mean Reciprocal Rank) を計測するスクリプトがあります。

- 評価用 CSV: `data/eval_queries.csv`（ヘッダ例: `query,qa_id`）
- 環境変数: `EVAL_QUERIES_CSV` にコンテナ内の CSV パスを指定できます。コンテナ実行時に `.env` 経由で注入してください。


例: `.env` を作成（`.env.example` をコピーして編集）

```bash
# Unix / WSL
cp .env.example .env

# PowerShell
Copy-Item .env.example .env
```

次に `.env` を開き、以下の環境変数を設定してください:

```
EVAL_QUERIES_CSV=eval_queries.csv
DATABASE_URL=postgresql://user:pass@host:5432/dbname
LMSTUDIO_EMBEDDING_URL=http://host.docker.internal:1234/v1/embeddings
MODEL_EMBEDDING=text-embedding-nomic-embed-text-v1.5@q8_0
```

実行方法:

- 開発インストールしてプロジェクトスクリプトを使う方法（推奨、一度だけ）:

```bash
python -m pip install -e web_backend
evaluate
```

- 直接モジュールを実行する方法:

```bash
python -m main.evaluate --top-k 10 --output /tmp/results.csv
```

実行時は `DATABASE_URL`, `LMSTUDIO_EMBEDDING_URL`, `MODEL_EMBEDDING` が環境に設定されている必要があります。出力に MRR が表示され、`--output` でクエリごとの順位情報を CSV に保存できます。

## Knowledge MCP サーバ

`knowledge_mcp/` は、既存の Q&A ナレッジベースを MCP（Model Context Protocol）経由で検索・管理するための独立サービスです（IMPL-202608041013 / ADR-0001〜0006）。既存 `web_backend` の `search_similar` はそのまま残し、並行運用します。

- トランスポート: Streamable HTTP（MCP エンドポイントは `/mcp`、ヘルスチェックは `/health`）
- 提供ツール:
  - `search_knowledge` … クエリの意味検索。`tags` / `category` フィルタ、`min_score` に対応
  - `list_tags` / `create_tag` / `rename_tag` / `move_tag` / `delete_tag` … タグマスタ管理（`tag` / `qa_tag` テーブル）
  - `set_tag_description` / `add_tag_alias` / `remove_tag_alias` … タグの説明文・同義語管理（IMPL-202608060837 / `tag_alias` テーブル）。`create_tag` / `rename_tag` は任意の `description` パラメータに対応。`list_tags` は `description` / `aliases` を含む
  - `list_qa` / `get_qa` / `create_qa` / `update_qa` / `list_categories` … QA管理（IMPL-202608060837 / ADR-0014）。`create_qa` は `question_text` から embedding を計算し、主となる `question_altered`（`is_primary=true`）を1件生成する

### 事前準備（DBスキーマ移行）

`title` 列・`tag` / `qa_tag` テーブル、および `question_altered.is_primary` 列の作成は、`db_hiroba_qa_init` サービスが `docker compose up` 時に自動的に適用します（IMPL-202608061016）。従来の手動 SQL 適用（`docker compose exec ... psql ...`）や `title` 補完バッチの手動実行は不要になりました。旧 `knowledge_mcp/migrations/` の内容は `db_hiroba_qa_init/migrations/` の単一マイグレーション履歴（`0003_add_title_and_tag_tables.sql`, `0004_add_question_altered_is_primary.sql`）へ統合済みです。

> 注: 現行の `data/exportjson_withguid.json` にはレコード単位の `tags` フィールドが無いため、`db_hiroba_qa_init` の補完処理では `title` のみが補完されます（タグ投入は 0 件）。

### 起動

```bash
docker compose up -d knowledge_mcp
# ヘルスチェック
curl -f http://localhost:${KNOWLEDGE_MCP_PORT:-8100}/health
```

`.env` 設定項目（`.env.example` 参照）:

| 項目 | 値の例 | 説明 |
|---|---|---|
| KNOWLEDGE_MCP_PORT | 8100 | Knowledge MCP サーバの対ホストポート |
| KNOWLEDGE_MCP_DEFAULT_TOP_K | 5 | `search_knowledge` の既定 top_k |

> セキュリティ: 本フェーズでは追加認証を実装していません（Open Issue #4, #10）。書き込み系のタグ管理ツールを含むため、社内ネットワーク外へポートを公開しないでください。

## Tag Selector MCP サーバ

`tag_selector_mcp/` は、質問文に最も関連する既存タグを選択するための独立サービスです（IMPL-202608051712 / ADR-0007〜0012）。Knowledge MCP が管理する `tag` テーブルを正本とし、`tag_alias`（同義語）と `tag.description` を用いて選択します。

- トランスポート: Streamable HTTP（MCP エンドポイントは `/mcp`、ヘルスチェックは `/health`）
- タグ選択方式（MVP, ADR-0009）: Alias 辞書によるルールベース照合 ＋ ローカルLLM（LM Studio）による一段階選択。Embedding 層・階層探索は未実装。
- 提供ツール:
  - `select_tags` … 質問文に関連するタグを `id` / `name` / `score` / `path` で score 降順に返す（`max_tags` / `confidence_threshold` に対応）
  - `list_taxonomy` … キャッシュ中のタグ知識ベース（`id` / `name` / `description` / `parent_tag_id` / `aliases`）を返す
  - `reload_taxonomy` … タグ知識ベースをDBから再読込し件数を返す
- タグ知識ベースは起動時ロード＋定期ポーリング（`TAXONOMY_RELOAD_INTERVAL_SEC`）＋ `reload_taxonomy` による明示リロードでメモリにキャッシュします（ADR-0011）。

### 事前準備（DBスキーマ移行・暫定シード）

`tag.description` 列・`tag_alias` テーブルの作成、および動作確認用の暫定 description / alias 投入は、`db_hiroba_qa_init` サービスが `docker compose up` 時に自動的に適用します（IMPL-202608061016）。従来の手動 SQL 適用・暫定シードスクリプトの手動実行は不要になりました。旧 `tag_selector_mcp/migrations/` の内容は `db_hiroba_qa_init/migrations/0005_add_tag_description_and_alias.sql` および `db_hiroba_qa_init` のシード処理へ統合済みです。

> 注: この暫定 description / alias は MVP 動作確認用のデータです。本番運用向けの網羅的な整備は Knowledge MCP 側のタグ管理ツール拡張後に別途行います（Open Issue #2）。

### 起動

LM Studio でチャット補完モデルをロードし、`.env` に接続情報を設定した上で起動します。

```bash
docker compose up -d tag_selector_mcp
# ヘルスチェック
curl -f http://localhost:${TAG_SELECTOR_MCP_PORT:-8200}/health
```

`.env` 設定項目（`.env.example` 参照）:

| 項目 | 値の例 | 説明 |
|---|---|---|
| TAG_SELECTOR_MCP_PORT | 8200 | Tag Selector MCP サーバの対ホストポート |
| LLM_PROVIDER | lmstudio | LLM 実装の切り替え（MVP は `lmstudio` のみ） |
| LMSTUDIO_CHAT_URL | http://host.docker.internal:1234/v1/chat/completions | LM Studio のチャット補完API（ベースURL・フルURLどちらでも可） |
| LMSTUDIO_CHAT_MODEL | （ロード済みモデル名） | チャット補完に使用するモデル名 |
| TAXONOMY_RELOAD_INTERVAL_SEC | 300 | タグ知識ベースの自動リロード間隔（秒） |
| TAG_SELECTOR_DEFAULT_MAX_TAGS | 3 | `select_tags` の既定 `max_tags` |
| TAG_SELECTOR_DEFAULT_CONFIDENCE_THRESHOLD | 0.0 | `select_tags` の既定 `confidence_threshold` |

> セキュリティ: 本フェーズでは追加認証を実装していません（Open Issue #6）。社内ネットワーク外へポートを公開しないでください。


## QA・タグ管理 UI（front_dev / web_backend 拡張）

`front_dev` の `/admin` 配下に、QAデータとタグ階層を登録・編集するための管理画面を追加しました（IMPL-202608060837 / ADR-0013〜0015）。`web_backend` が MCP クライアントとして Knowledge MCP のツールを呼び出す BFF（`/api/*`）を提供し、`chatbot_db` への直接書き込みは行いません。

- 画面（`react-router-dom` を `/admin` 配下のみで使用。既存3画面の分岐方式は不変）:
  - `http://localhost:5173/admin/qa` … QA一覧（キーワード・カテゴリ・タグで絞り込み、ページング）
  - `http://localhost:5173/admin/qa/new` … QA新規登録
  - `http://localhost:5173/admin/qa/:id` … QA編集
  - `http://localhost:5173/admin/tags` … タグ階層（作成・名称変更・説明編集・親変更・削除。同義語は表示のみ）
- BFF API（`web_backend`、`/api` プロキシ経由）:
  - `GET/POST /api/qa`, `GET/PUT /api/qa/{id}`, `GET /api/categories`
  - `GET/POST /api/tags`, `PUT/DELETE /api/tags/{id}`
- タグ削除は、`qa_tag` 参照・子タグ存在時は拒否され、削除可能な場合は紐づく `tag_alias` も連動削除されます。

### 事前準備

Knowledge MCP サーバ（上記）が起動していることが前提です。`question_altered.is_primary` 列を含むスキーマ移行は `db_hiroba_qa_init` が自動適用します（IMPL-202608061016）。`web_backend` は `KNOWLEDGE_MCP_URL` で Knowledge MCP へ接続します。

`.env` 設定項目（`.env.example` 参照）:

| 項目 | 値の例 | 説明 |
|---|---|---|
| KNOWLEDGE_MCP_URL | http://knowledge_mcp:8100/mcp | `web_backend` が接続する Knowledge MCP のエンドポイント |

### 起動

```bash
docker compose up -d knowledge_mcp web_backend frontend
```

ブラウザで `http://localhost:5173/admin/qa` を開きます。`web_backend` は `knowledge_mcp` のヘルスチェック完了後に起動します（`depends_on`）。

> セキュリティ: 本フェーズでは書き込み系API（QA・タグの登録編集削除）に追加認証を実装していません（Open Issue #2）。社内ネットワーク外へ公開しないでください。
