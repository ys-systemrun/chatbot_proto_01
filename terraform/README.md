# terraform/ — MCPサーバー・クライアント AWS デプロイ

実装指示書 `docs/implementation_handoff/202608181432_implementation.md`（IMPL-202608181432）および
ADR-0039 に基づく Terraform 構成。ECS Fargate + RDS(pgvector) + ECR による AWS 内部限定デプロイ（検証環境）。
state を **database 構成 / app 構成の2層**に分割する（ADR-0039。旧 3 層 network/database/app を統合）。

> **実行系（ADR-0040）**: デプロイ処理は **Docker コンテナ内の Python オーケストレータ**（`terraform/deploy/`）が担う。
> `.bat` のダブルクリック起動は維持（`.bat` は `docker run` の薄いラッパ）。ホストは **Docker Desktop だけ**あればよく、
> terraform / aws CLI のホスト導入は不要（イメージに同梱）。旧 `scripts/*.ps1`（PowerShell 5.1）は廃止。

> **前提（着手前に必須）**
> - 全設定を単一の `terraform/.env` に記入（ADR-0040）。AWS 認証（`AWS_ACCESS_KEY_ID` 等）・共通値（`AWS_REGION` / `AWS_ACCOUNT_ID` / `STATE_BUCKET`）・**全 terraform 変数**（`TF_VAR_*`）を含む。`terraform.tfvars` は廃止（`terraform/.env.example` がテンプレート）。
> - 既存 VPC/サブネットの ID（`TF_VAR_vpc_id` / `TF_VAR_private_subnet_ids`）を基盤チームから受領（ADR-0036）→ `terraform/.env`。
> - **イメージビルド前に、Bedrock 切り替えのアプリ実装（IMPL-202608101616）が完了していること。**
>   未完了だと AWS 上のコンテナが LM Studio へ到達を試みて失敗する。

## ディレクトリ構成

state を2構成に分割（ADR-0039）。依存は database ← app の一方向（app が `terraform_remote_state` で database の出力を参照）。

```
terraform/
├── bootstrap/                Phase 0: state 用 S3 バケット（メイン構成の外で管理, 循環依存回避）
├── main/
│   ├── database/             [database構成] ネットワーク基盤 + RDS(pgvector) + シード用 ECS 周辺
│   │   ├── backend.tf        （旧 verify-network + verify-database + verify の db_init 部分を統合）
│   │   ├── variables.tf
│   │   ├── main.tf
│   │   └── outputs.tf
│   └── app/                  [app構成] アプリ側 ECS 常駐サービス周辺
│       ├── backend.tf
│       ├── variables.tf
│       ├── main.tf
│       └── outputs.tf
├── modules/
│   ├── network/          既存VPC/サブネットを data 参照し SG・VPCエンドポイントを作成（ADR-0036）
│   ├── ecr/              ECR リポジトリ（database で1件, app で4件に分割呼び出し）
│   ├── database/         RDS PostgreSQL(pgvector) + DATABASE_URL シークレット（§5.3）
│   ├── ecs-cluster/      Fargate クラスタ（§5.4）
│   ├── ecs-service/      常駐サービス共通（app で3回呼び出し）（§5.5）
│   ├── db-init-task/     db_hiroba_qa_init の Run Task 定義（database 構成が呼び出し）（§5.6）
│   ├── service-discovery/ ECS Service Connect 名前空間（§5.5）
│   ├── mcp-inspector-task/ MCP Inspector 検証用タスク（app 構成）（§5.7）
│   └── cost-alert/       Bedrock 月額予算アラート（AWS Budgets）（app 構成）
├── deploy/                  デプロイオーケストレータ（コンテナ内 Python, ADR-0040）
│   ├── Dockerfile          python3.11 + terraform(ピン) + docker CLI
│   ├── pyproject.toml      依存は boto3 のみ
│   ├── run.bat             共通ランナー（*.bat から call。build→docker run）
│   ├── src/                config / aws / tf / dockercli / tfvars / prompts / commands / __main__
│   └── tests/              pytest（config / tfvars / gate）
├── .env.example            → .env にコピーして全設定を記入（AWS 認証 + STATE_* + 全 TF_VAR_*）
└── .env                    実設定（Git 管理外。terraform/ 直下, ADR-0040）
```

> `modules/database`（RDS リソース定義のモジュール）と `main/database`（database 構成の root）は
> 名称が似ているため、ログ・会話では「db モジュール」「database 構成」等で呼び分けること（ADR-0039 §10）。

**state 分割の要点（ADR-0039）:**
- **database 構成**: 既存VPC参照 + SG + VPCエンドポイント（旧 network）、RDS + DBサブネットグループ + `DATABASE_URL` シークレット（旧 database）、`db_hiroba_qa_init` シードタスク定義 + シード用 ECR 1件（旧 app から移設）。RDS を永続化（`deletion_protection=true` 既定）。**通常の `destroy-app` の対象外**（再シード＝Bedrock 再計算を避ける）。
- **app 構成**: database 構成の出力（VPC/サブネット・各 SG・`db_url_secret_arn`）を `terraform_remote_state` で参照。ECS クラスタ + 3常駐サービス + MCP Inspector タスク定義 + 予算アラート + 残り4リポジトリの ECR。`destroy-app` はこの構成のみ破棄。

## かんたん実行（bat ダブルクリック）

`apply-all.bat` を使うと、前提チェック → **database 構成 apply（ネットワーク+RDS+シード用ECR/イメージ）** →
app 構成 apply（ECR 作成 → docker build/push → apply、ゲート閉 `knowledge_mcp=0`）→ シード run-task
（exitCode=0 待機）→ app 構成 再 apply（ゲート開 `knowledge_mcp=1`）までを一括実行する。
Phase 4→5 のゲート（seed 完了まで knowledge_mcp を起動しない）もスクリプト内で担保する。

```
terraform/
├── bootstrap.bat        Phase 0 前半のみ（state 用 S3 バケット作成。バケット名は .env の STATE_BUCKET）
├── apply-database.bat   database 構成のみ apply（ネットワーク+RDS+シード用イメージ）
├── apply-app.bat        app 構成のみ apply（要: database 構成 apply 済み）
├── apply-all.bat        フルパイプライン（database → app閉 → seed → app開）
├── seed.bat             シード run-task のみ実行（再シード用途。要: 両構成 apply 済み）
├── migrate.bat          マイグレーション専用 run-task（シード投入をスキップ。ADR-0075。要: 両構成 apply 済み）
├── destroy-app.bat      app 構成のみ破棄（RDS は残す。'destroy-app' 入力の確認あり）
├── destroy-database.bat database 構成を破棄（RDS 削除。'destroy-database' 入力の確認あり）
├── deploy/                 コンテナ内 Python オーケストレータ（ADR-0040。*.bat の実体）
├── .env.example            → .env にコピーして全設定を記入（Git 管理外）
└── .env                    実設定（terraform/ 直下, Git 管理外）
```

> 各 `.bat` は `deploy/run.bat` を呼び、初回だけイメージ（`chatbot-deploy:latest`）を build してから
> `docker run`（リポジトリを `/work` にマウント、ホスト Docker ソケットを共有）で `deploy <コマンド>` を実行する。

**初回だけ手動で必要な準備（これ以降は bat クリックのみ）:**

1. **Docker Desktop を起動**（実行系のイメージビルドと DooD のため必須。terraform / aws CLI のホスト導入は不要）。
2. `terraform/.env` … `terraform/.env.example` をコピーして全設定を記入（ADR-0040 で単一ファイルに集約）:
   - **AWS 認証**: `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`（一時クレデンシャルなら `AWS_SESSION_TOKEN` も）。鍵の代わりに `AWS_PROFILE` も可（両方あれば鍵優先）。**平文保持のためコミット厳禁・ローカル限定。可能なら一時クレデンシャル推奨。**
   - **共通値**: `AWS_REGION`、`AWS_ACCOUNT_ID`（認証先不一致時に安全停止）、`STATE_BUCKET`（既定 `chatbot-invitro-terraform-state-349131272460-us-east-1-an`, ADR-0039）、`NAME_PREFIX`（既定 `chatbot-invitro`）、`STATE_KEY_DATABASE` / `STATE_KEY_APP`（既定のままでよい）。
   - **terraform 変数（`TF_VAR_*`）**: 旧 `terraform.tfvars` の内容をすべてここに記入。`TF_VAR_vpc_id` / `TF_VAR_private_subnet_ids`（既存 VPC/サブネット, ADR-0036）、`TF_VAR_rds_engine_version`（pgvector 対応版を要確認）、`TF_VAR_bedrock_chat_model_id` / `TF_VAR_bedrock_embedding_model_id` / `TF_VAR_embedding_vector_dim`（共有・同値）、`TF_VAR_service_namespace`、予算アラート等。リストは JSON（`["subnet-a","subnet-b"]`）、値の後ろにコメントを書かないこと。
   > **ADR-0040**: 設定は単一 `.env` に集約する。`deploy` が `AWS_*`/`STATE_*` をマッピングし、`TF_VAR_*` は terraform へ素通しする。terraform は未宣言の `TF_VAR_*` を無視するため両構成の変数を1ファイルに置いてよい。実行時上書き（`deletion_protection` / `knowledge_mcp_desired_count` 等）は `deploy` が `-var` で行う。

> `.env` が無い/必須変数が欠けている場合、`deploy` は雛形生成の案内や必須項目を表示して安全に停止する。値を埋めて再度クリックすれば続行できる。
> 無人/CI 向けには `deploy` の各 apply 系コマンドに `--yes` を付ける（`.bat` を編集するか `run.bat` 経由で引数を渡す）。
>
> **完全自動化できない範囲:** Phase 6 の検証（MCP Inspector の `tools/list`・`agent_invitro` の `ipython` 手動テストクエリ3件）は対話操作のため bat 対象外。下記「実行手順」の Phase 6 を手動で行う。MCP Inspector 検証イメージ（`mcp-inspector` リポジトリ）も別途手動ビルド・push が必要（§5.7）。

> **ADR-0040**: 実行系は Docker コンテナ内 Python（`terraform/deploy/`）。terraform は**コンテナ内（Linux）**で実行されるため、`.terraform.lock.hcl` に `linux_amd64` のプロバイダハッシュが必要（`terraform providers lock -platform=linux_amd64 -platform=windows_amd64` で両対応にしておく）。手動で terraform を叩きたい場合は `deploy shell`（環境設定済みのコンテナ内 bash）から行う。

## 実行手順（Phase 別）

> 通常は各 `.bat` のダブルクリックだけでよい（内部で `deploy <コマンド>` が下記を自動実行する）。
> 以下は `deploy` が各 Phase で行う処理の説明（`docker run` 相当）。CLI から直接叩く場合は
> `deploy/run.bat <コマンド>`（例: `deploy\run.bat apply-database`）でも実行できる。
>
> **手動で terraform を叩きたい場合（ADR-0040）**: `deploy shell` で環境設定（`TF_VAR_*` エクスポート）済みの
> コンテナ内 bash に入り、`cd main/database && terraform plan` のように実行する。ホストで直接 terraform は実行しない
> （プロバイダが Linux 用のため。旧 `load-env.ps1` の dot-source は不要になった）。

### Phase 0: ブートストラップ（state バケット）

**state バケット作成は `bootstrap.bat` のダブルクリックで実行できる。**
バケット名は `terraform/.env` の `STATE_BUCKET`、リージョンは `AWS_REGION` から供給される（コマンドラインに直書きしない）。既にバケットがあればスキップする。

```
terraform/bootstrap.bat   ← ダブルクリック（内部で deploy bootstrap を実行）
```

> **バケット名について（account-regional 名前空間, ADR-0039）**: 既定の `STATE_BUCKET`
> `chatbot-invitro-terraform-state-349131272460-us-east-1-an` は末尾 `-an` の
> account-regional 名前空間バケット（`{prefix}-{account-id}-{region}-an`）。この形式は AWS
> プロバイダ **>= 6.37** が必要で、`bootstrap/main.tf` の `aws_s3_bucket` に
> `bucket_namespace = "account-regional"` を指定してある。プロバイダが古いと
> `Unsupported argument`、指定が無いと `is an account-regional namespace bucket` 検証エラーになる。
> 従来のグローバル名前空間で作る場合は `.env` の `STATE_BUCKET` から `-an` を外し、
> `bucket_namespace` 行も削除する。

> `deploy bootstrap` は内部で bootstrap 構成を `terraform init` → `terraform apply`（`-var aws_region=... -var state_bucket_name=...`）する（`.env` の値を使用）。CLI からは `deploy\run.bat bootstrap` でも実行できる。

事前準備は `terraform/.env` の記入のみ（旧 `terraform.tfvars` のコピーは不要。ADR-0040 で `.env` に集約）。

### Phase 1: database 構成（ネットワーク + RDS + シード用イメージ）
`apply-database.bat` が次を自動化する（手動なら以下を database ディレクトリで実行）:
```bash
cd terraform/main/database
terraform init -backend-config="bucket=<state-bucket>" -backend-config="region=<region>" \
  -backend-config="key=database/state.tfstate" -backend-config="use_lockfile=true"
terraform apply -target=module.ecr          # シード用 ECR(db-hiroba-qa-init) を先行作成
terraform output ecr_repository_urls        # push 先 URI を確認

aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <acct>.dkr.ecr.<region>.amazonaws.com
docker build -t <acct>.dkr.ecr.<region>.amazonaws.com/db-hiroba-qa-init:latest ../../../db_hiroba_qa_init
docker push  <acct>.dkr.ecr.<region>.amazonaws.com/db-hiroba-qa-init:latest

terraform apply                             # RDS/ネットワーク/シードタスク定義を作成
```

### Phase 2: app 構成の ECR + イメージ push
`apply-app.bat` が次を自動化する（手動なら app ディレクトリで実行）:
```bash
cd terraform/main/app
terraform init -backend-config="bucket=<state-bucket>" -backend-config="region=<region>" \
  -backend-config="key=app/state.tfstate" -backend-config="use_lockfile=true"
terraform apply -target=module.ecr          # 4リポジトリを先行作成
terraform output ecr_repository_urls

aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <acct>.dkr.ecr.<region>.amazonaws.com
for c in knowledge_mcp tag_selector_mcp agent_invitro; do
  repo=$(echo $c | tr '_' '-')
  docker build -t <acct>.dkr.ecr.<region>.amazonaws.com/$repo:latest ../../../$c
  docker push  <acct>.dkr.ecr.<region>.amazonaws.com/$repo:latest
done
# MCP Inspector 検証イメージ（mcp-inspector）は Phase 6 用に別途ビルドして push（§5.7）
```

### Phase 3: app 構成 apply（ゲート閉）
```bash
cd terraform/main/app
terraform apply -var="knowledge_mcp_desired_count=0"   # seed 完了まで knowledge_mcp を起動しない
```

### Phase 4: データ投入（シード, knowledge_mcp 起動より前に完了させる）
ECS には compose の `depends_on: service_completed_successfully` に相当する自動待機が無いため、
順序は手順で担保する。`seed.bat` が次を自動化する（両構成の output を参照して run-task）:
```bash
# database 構成から subnets/SG/タスク定義ファミリ、app 構成から cluster_name を取得
CLUSTER=$(cd ../app && terraform output -raw cluster_name)
SUBNETS=$(terraform output -json private_subnet_ids | jq -r 'join(",")')   # database 構成で
SG=$(terraform output -raw sg_verification_task_id)                        # database 構成で
TD=$(terraform output -raw db_init_task_family)                            # database 構成で

aws ecs run-task --cluster $CLUSTER --launch-type FARGATE \
  --task-definition $TD --enable-execute-command \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=DISABLED}"

# CloudWatch Logs /ecs/db-hiroba-qa-init でマイグレーション・シードを確認し、exitCode=0 を確認
aws ecs describe-tasks --cluster $CLUSTER --tasks <task-arn> --query 'tasks[].containers[].exitCode'
```

> **スキーマ変更のみを反映したい場合（ADR-0075）**: `migrate.bat`（または `seed --skip-seed`）を使う。
> `seed` と同じ `db_init_task_family` を `MIGRATE_ONLY=true` の environment オーバーライドで起動し、
> シード投入（QA原本・言い換え質問・カテゴリ、embedding 計算を伴いうる手順）だけをスキップして、
> ロール作成・両DBのマイグレーション適用・権限付与・エクスポート専用ロール作成は通常どおり実行する。
> 非破壊的・冪等（何度実行しても未適用分のみ適用）で確認プロンプトなし。使い分け:
> スキーマ反映=`migrate`、データ投入・更新=`import-data`、初回や再シード=`seed`（オプションなし）。

### Phase 5: app 構成 再 apply（ゲート開）
**exitCode=0 を確認してから** knowledge_mcp サービスを稼働させる:
```bash
cd terraform/main/app
terraform apply -var="knowledge_mcp_desired_count=1"
```

### Phase 6: 検証（手動）
```bash
# プロトコル層: MCP Inspector（ADR-0029）。事前に mcp-inspector イメージを build/push しておく（§5.7）
aws ecs run-task --cluster $CLUSTER --launch-type FARGATE \
  --task-definition $(cd ../app && terraform output -raw mcp_inspector_task_family) --enable-execute-command \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=DISABLED}"
aws ecs execute-command --cluster $CLUSTER --task <task-arn> --container mcp-inspector --command "/bin/sh" --interactive
#   → Service Connect 名で tag_selector_mcp:8200 / knowledge_mcp:8100 に tools/list, tools/call

# クライアント統合層: agent_invitro（ADR-0025）
aws ecs execute-command --cluster $CLUSTER --task <agent-task-arn> --container agent_invitro --command "ipython" --interactive
#   → 会話エージェント実験要件定義書 §6.4 の手動テストクエリ3件を実行
```

### admin_ui（QA・タグ管理UI, ADR-0041/0042 / IMPL-202608211050）
`app` 構成に含まれる（`apply-app` / `apply-all` で同時に作成される）。`web_backend`（FastAPI）に
`front_dev` の本番ビルドを同梱した単一イメージ（`web_backend/Dockerfile.admin_ui`, ビルドコンテキストは
リポジトリルート）を、internet-facing ALB 経由で社内IP限定公開する。

事前に `.env` で以下を設定すること（未設定だと ALB に誰も到達できない / 配置できない）:
- `TF_VAR_admin_ui_allowed_cidrs` … 到達を許可する社内IP（CIDR リスト）。発注者から受領（0章 Open Issue #1）。
- `TF_VAR_public_subnet_ids` … ALB を置く既存パブリックサブネット。基盤チームに確認（0章 Open Issue #2）。

ブラウザからのアクセス先（ALB DNS 名）は apply 後に output で確認する:
```bash
cd terraform/main/app
terraform output -raw admin_ui_alb_dns_name
# → http://<dns_name>/ を社内ネットワークのブラウザで開く（QA一覧 / タグ階層 / 登録編集）
```
本フェーズは HTTP(80) のみ（HTTPS は次フェーズ, 0章暫定方針 / 11章 Open Issue #1）。

### 破棄（コスト管理 / ADR-0039）
DB を残したまま常時課金リソース（ECS 等）だけ止めるのが通常運用。
**destroy 順序は app → database（逆順は依存関係違反で失敗する, §10）。**
```bash
# app 構成のみ（RDS/ネットワークは残る）= destroy-app.bat（deploy destroy-app）と同じ
# deploy が内部で行う処理（手動なら deploy shell 内で実行）:
cd main/app
terraform destroy -var="knowledge_mcp_desired_count=0"
```
DB も破棄する場合（プロジェクト完全終了時）は **app を先に破棄してから** destroy-database.bat か、database 構成で明示的に:
```bash
cd terraform/main/database
terraform apply   -var="deletion_protection=false"  # 削除保護を解除
terraform destroy -var="deletion_protection=false" -var="skip_final_snapshot=true"
```
> **VPC エンドポイントは課金対象**（Interface型は毎時課金）。VPCエンドポイントは database 構成に含まれるため、
> `destroy-database` で一緒に削除される（既存VPC/サブネット自体は data 参照のため削除されない）。

## 注意点
- **既存 VPC 前提（ADR-0036）**: database 構成は VPC/サブネットを新規作成しない。`vpc_id` / `private_subnet_ids` を基盤チームから受領し、既存サブネットが要件（2AZ以上、DBサブネットグループ用、十分な空きIP）を満たすか確認すること。
- **今回は「移行」ではなく「新規作成」（ADR-0039）**: 実 AWS 環境・S3 上の旧 state は存在しない前提のため、`terraform state mv` やインポート作業は不要。
- **database 構成内は `terraform_remote_state` を使わない（§10）**: network/database/db-init-task が同一 root に統合されたため、モジュール間の値受け渡しは通常のモジュール出力参照（`module.network.xxx`）で完結する。`terraform_remote_state` は app 構成から database 構成を参照する片方向のみ。
- **backend ブロックは変数を参照できない（§10）**: `bucket`/`key`/`region` を `backend.tf` に直書きせず、必ず `-backend-config` で渡す（スクリプトは `.env` の値を注入）。
- **適用順（ADR-0039）**: database → app の順で apply（`apply-all.bat` が担保）。app 構成は `terraform_remote_state` で database の出力を参照するため、database を先に apply していないと参照が解決できない。
- **destroy 順序（ADR-0039 §10）**: app → database の逆順が必須。app の ECS が database の SG/サブネットを使用中だと database の destroy が依存関係違反で失敗する。`destroy-database` は app 構成の state を検出して警告する。
- **DB は destroy-app の対象外（ADR-0037 継承）**: RDS は永続化（`deletion_protection=true`）。DB 破棄は destroy-database.bat / database 構成で明示的に（保護解除→destroy の2段階）行う。
- **ECS Exec は事後有効化不可**: `enable_execute_command` は最初から true（agent_invitro / 検証タスク）。
- **pgvector 対応バージョン**: `rds_engine_version` は実装着手時に AWS 公式で要確認。
- **Service Connect タイムアウト**: Streamable HTTP(SSE) の長時間コネクションは Envoy 既定タイムアウトが短い可能性。Phase 6 で併せて確認。
- **DATABASE_URL**: アプリが1本の URL を要求するため、`database` モジュールが random_password から完全な接続 URL を組み立てた独自シークレットを作り、ECS に secrets 注入する（RDS マネージドマスターパスワードは JSON のため URL 注入に使えない）。
- **admin_ui の ALB コスト（ADR-0041）**: ALB は時間課金＋LCU で常時発生する。`admin_ui`・ALB は `app` 構成に含まれるため `destroy-app` で ECS 等と一緒に破棄される（RDS は残る）。検証終了後にコストを止めたい場合は `destroy-app` を実行する。
- **admin_ui タスクは非公開（ADR-0041 T13）**: ALB はパブリックサブネットだが、`admin_ui` の ECS タスク自体はプライベートサブネット・`assign_public_ip=false`（既存3サービスと同じ）。ALB SG からのコンテナポートのみ受ける。
- **ローカル docker-compose は不変（ADR-0042）**: `Dockerfile.admin_ui` は AWS 専用の追加ファイル。既存 `web_backend/Dockerfile`・`front_dev/Dockerfile`・`docker-compose.yml` は変更しないため、ローカル開発フローに影響しない。
- **CSV/JSON データ（ADR-0034）**: ECS にホストマウントは無いが、シード元データは db-hiroba-qa-init イメージに `/data` として同梱済み（`Dockerfile` の `COPY data /data`）。EFS 等の追加ストレージは不要。`CSV_DATA_DIR` は `data`（main.py が先頭に `/` を付与 → `/data`）。
