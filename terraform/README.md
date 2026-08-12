# terraform/ — MCPサーバー・クライアント AWS デプロイ

実装指示書 `docs/implementation_handoff/202608101542_implementation.md`（IMPL-202608101542）に基づく
Terraform 構成。ECS Fargate + RDS(pgvector) + ECR による AWS 内部限定デプロイ（検証環境）。

> **前提（着手前に必須, §0/§12）**
> - AWS アカウントID・リージョンの実値を発注者から受領（Open Issue #6）→ `terraform.tfvars`。
> - **Phase 3（イメージビルド）前に、Bedrock 切り替えのアプリ実装（IMPL-202608101616）が完了していること。**
>   未完了だと AWS 上のコンテナが LM Studio へ到達を試みて失敗する。

## ディレクトリ構成

```
terraform/
├── bootstrap/            Phase 0: state 用 S3 バケット（メイン構成の外で管理, §10 循環依存回避）
├── envs/verify/          メイン構成（各モジュール呼び出し・backend・tfvars）
└── modules/
    ├── network/          VPC・プライベートサブネット・SG・VPCエンドポイント（§5.1）
    ├── ecr/              ECR リポジトリ×5（4コンポーネント + inspector）（§5.2）
    ├── database/         RDS PostgreSQL(pgvector) + DATABASE_URL シークレット（§5.3）
    ├── ecs-cluster/      Fargate クラスタ（§5.4）
    ├── ecs-service/      常駐サービス共通（3回呼び出し）（§5.5）
    ├── db-init-task/     db_hiroba_qa_init の Run Task 定義（§5.6）
    ├── service-discovery/ ECS Service Connect 名前空間（§5.5）
    └── mcp-inspector-task/ MCP Inspector 検証用タスク（§5.7）
```

## かんたん実行（bat ダブルクリック）

`deploy.bat` を使うと、前提チェック → ECR 作成 → docker build/push → apply →
db_init の run-task → 完了待機（exitCode=0）→ knowledge_mcp 起動 までを一括実行する。
Phase 4→5 のゲート（seed 完了まで knowledge_mcp を起動しない）もスクリプト内で担保する。

```
terraform/
├── deploy.bat          ダブルクリックでフルパイプライン実行
├── destroy.bat         ダブルクリックで一括破棄（'destroy' 入力の確認あり）
└── scripts/
    ├── deploy.ps1 / destroy.ps1 / common.ps1
    └── .env.example         → .env にコピーして記入（Git 管理外）
```

**初回だけ手動で必要な準備（これ以降は bat クリックのみ）:**

1. `scripts/.env` … `deploy.bat` 初回実行時に `.env.example` から雛形が自動生成される。`STATE_BUCKET`（state 用 S3 バケット名、グローバル一意）と AWS 認証情報（`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`、一時クレデンシャルなら `AWS_SESSION_TOKEN` も）を記入。`AWS_ACCOUNT_ID` を入れると認証先アカウント不一致時に安全停止する。鍵の代わりに `AWS_PROFILE` を使う運用も可（両方あれば鍵優先）。**この `.env` は AWS 認証情報を平文で保持するためコミット厳禁・ローカル限定。可能なら一時クレデンシャル推奨。**
2. `envs/verify/terraform.tfvars` … 同じく初回実行時に雛形が自動生成される。発注者受領値（`aws_account_id` / `aws_region`）、Bedrock モデルID（`bedrock_chat_model_id` / `bedrock_embedding_model_id`）、`embedding_vector_dim` 等を記入。
3. Docker Desktop 起動、`terraform`/`aws` CLI を PATH に（AWS 認証は上記 `.env` で供給される。`.env` に鍵/プロファイルが無ければ既定のクレデンシャルチェーンを使用）。

> 上記のうち 1・2 が未記入だと `deploy.bat` は雛形を生成して安全に停止する。値を埋めて再度クリックすれば続行できる。
> `deploy.ps1 -AutoApprove` で確認プロンプトを省略可能（無人/CI 向け）。
>
> **完全自動化できない範囲:** Phase 6 の検証（MCP Inspector の `tools/list`・`agent_invitro` の `ipython` 手動テストクエリ3件）は対話操作のため bat 対象外。下記「実行手順」の Phase 6 を手動で行う。MCP Inspector 検証イメージ（`mcp-inspector` リポジトリ）も別途手動ビルド・push が必要（§5.7）。

> スクリプトは Windows PowerShell 5.1 互換。`.ps1` は UTF-8 (BOM 付き) で保存すること（日本語コメントの文字化け・構文エラー防止）。

## 実行手順（Phase 別, §4/§7/§8）

### Phase 0: ブートストラップ
```bash
cd terraform/bootstrap
terraform init
terraform apply -var="aws_region=<region>" -var="state_bucket_name=<globally-unique>"
# create_lock_table=true を付けるのは Terraform < 1.10 のときのみ
```
`envs/verify` で使う `terraform.tfvars` を用意:
```bash
cd ../envs/verify
cp terraform.tfvars.example terraform.tfvars   # 実値を編集（Git 管理外）
```

### Phase 0→3: ECR 作成 + イメージ push
`terraform apply` で ECR も作られるが、ECS サービスはイメージが無いと起動しない。
まず ECR だけ先に作り、イメージを push してから全体を apply するのが安全:
```bash
terraform init -backend-config="bucket=<state-bucket>" -backend-config="region=<region>"
terraform apply -target=module.ecr
terraform output ecr_repository_urls   # push 先 URI を確認

# 各コンポーネント（既存 Dockerfile をそのまま利用, §5.2）
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <acct>.dkr.ecr.<region>.amazonaws.com
for c in knowledge_mcp tag_selector_mcp agent_invitro db_hiroba_qa_init; do
  repo=$(echo $c | tr '_' '-')
  docker build -t $repo ./$c
  docker tag $repo:latest <acct>.dkr.ecr.<region>.amazonaws.com/$repo:latest
  docker push <acct>.dkr.ecr.<region>.amazonaws.com/$repo:latest
done
# MCP Inspector 検証イメージ（mcp-inspector）も別途ビルドして push（§5.7）
```

### Phase 1〜5: 本体 apply
```bash
terraform apply    # VPC / RDS / クラスタ / タスク定義 / サービス
```

### Phase 4: データ投入（knowledge_mcp 起動より前に完了させる, §7/§8.1）
ECS には compose の `depends_on: service_completed_successfully` に相当する自動待機が無いため、
順序は手順で担保する:
```bash
CLUSTER=$(terraform output -raw cluster_name)
SUBNETS=$(terraform output -json private_subnet_ids | jq -r 'join(",")')
SG=$(terraform output -raw sg_verification_task_id)
TD=$(terraform output -raw db_init_task_family)

aws ecs run-task --cluster $CLUSTER --launch-type FARGATE \
  --task-definition $TD --enable-execute-command \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=DISABLED}"

# CloudWatch Logs でマイグレーション・シードを確認し、exitCode=0 を確認（§8.1）
aws ecs describe-tasks --cluster $CLUSTER --tasks <task-arn> \
  --query 'tasks[].containers[].exitCode'
```
**exitCode=0 を確認してから** knowledge_mcp サービスを稼働させる（既に apply 済みなら強制再デプロイ or desired_count 調整で起動タイミングを制御）。

### Phase 6: 検証（§8.2/§8.3）
```bash
# プロトコル層: MCP Inspector（ADR-0029）
aws ecs run-task --cluster $CLUSTER --launch-type FARGATE \
  --task-definition $(terraform output -raw mcp_inspector_task_family) --enable-execute-command \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=DISABLED}"
aws ecs execute-command --cluster $CLUSTER --task <task-arn> --container mcp-inspector \
  --command "/bin/sh" --interactive
#   → Service Connect 名で tag_selector_mcp:8200 / knowledge_mcp:8100 に tools/list, tools/call

# クライアント統合層: agent_invitro（ADR-0025）
aws ecs execute-command --cluster $CLUSTER --task <agent-task-arn> --container agent_invitro \
  --command "ipython" --interactive
#   → 会話エージェント実験要件定義書 §6.4 の手動テストクエリ3件を実行
```

### 破棄（コスト管理, §10）
```bash
terraform destroy
```

## 注意点（§10）
- **ECS Exec は事後有効化不可**: `enable_execute_command` は最初から true（agent_invitro / 検証タスク）。
- **pgvector 対応バージョン**: `rds_engine_version` は実装着手時に AWS 公式で要確認。
- **Service Connect タイムアウト**: Streamable HTTP(SSE) の長時間コネクションは Envoy 既定タイムアウトが短い可能性。§8.2/8.3 で併せて確認。
- **DATABASE_URL**: アプリが1本の URL を要求するため、`database` モジュールが random_password から
  完全な接続 URL を組み立てた独自シークレットを作り、ECS に secrets 注入する（RDS マネージド
  マスターパスワードは JSON のため URL 注入に使えない）。
- **CSV/JSON データ（ADR-0034）**: ECS にホストマウントは無いが、シード元データは
  db-hiroba-qa-init イメージに `/data` として同梱済み（`Dockerfile` の `COPY data /data`）。
  EFS 等の追加ストレージは不要。`CSV_DATA_DIR` は `data`（main.py が先頭に `/` を付与 → `/data`）。
