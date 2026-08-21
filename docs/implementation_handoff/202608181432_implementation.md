# Terraform構成再編（3層→2層統合） 実装指示書

- 文書番号: IMPL-202608181432
- 対象プロジェクト: chatbot_invitro
- 参照文書:
  - 要件定義書 `docs/requirement/202608180957_Terraform構成再編要件定義書.md`（REQ-202608180957、ステータス: Confirmed。15章の残オープンイシューは本書0章・11章に引き継ぐ）
  - ADR `docs/adr/0039-terraform-state-two-layer-consolidation.md`（本再編のために新設、ステータス: Accepted）
  - 関連（既存）: ADR-0023〜0031, 0034, 0036, 0037, 0038（いずれも内容変更なし。リソースがどのTerraform rootに属するかの再配置のみ）
- 対象コンポーネント: `terraform/`配下全体（既存の3層構成を削除し、`main/database`・`main/app`の2層構成として作り直す）。`knowledge_mcp`等のアプリケーションコード自体への変更はなし。
- 本書の位置づけ: 要件定義書・ADR-0039で確定した方針を、実装担当者（インフラ担当者またはコーディングエージェント）が着手できる粒度まで具体化した指示書である。**本書自体はTerraformコード・スクリプトコードを含まない**（ディレクトリ構成・リソース仕様・変数一覧・作業手順の指示にとどめる）。実際の`.tf`/`.ps1`/`.bat`ファイルの作成・編集は、別途担当者が本書の指示に従って行うこと。

## 0. 本書作成にあたり確定した事項

要件定義書のオープンイシューのうち、本書作成までに確認・確定した項目を整理する。

| 項目 | 決定内容 | 根拠・備考 |
|---|---|---|
| state分割の単位 | 現行3層（network/database/app）を2層（database構成/app構成）に統合 | ADR-0039 |
| ディレクトリ名 | `terraform/envs/`→`terraform/main/`に改称。配下は`database/`・`app/` | 利用者確認済み（2026-08-18） |
| stateバケット名（既定値） | `chatbot-invitro-terraform-state-349131272460-us-east-1-an` | 利用者確認済み（2026-08-18） |
| state key（既定値） | database構成: `database/state.tfstate` / app構成: `app/state.tfstate` | 利用者確認済み（2026-08-18） |
| stateバケット名・keyの注入方法 | `.tf`ファイル・スクリプトへの直書きを避け、`scripts/.env`から供給する（詳細は5.1節・6章） | 利用者確認済み（2026-08-18） |
| 既存AWS環境の状況 | 実デプロイ実績なし。state移行は不要で、既存`terraform/`配下を削除して作り直せばよい | 利用者確認済み（2026-08-18） |
| `modules/cost-alert`（Bedrock予算アラート）の帰属 | app構成 | 利用者確認済み（2026-08-18） |
| `modules/mcp-inspector-task`の帰属 | app構成（暫定） | 要件定義書15章オープンイシュー#3。本書11章に引き継ぐ |

残るオープンイシューは11章にまとめる。いずれも実装の一部を暫定方針で進めつつ、実装完了までに確定させればよい項目であり、着手をブロックするものではない。

## 1. 全体作業フェーズ

| Phase | 目的 | 主な成果物 | 前提 |
|---|---|---|---|
| Phase 1 | 既存構成の削除 | `terraform/envs/`・旧`*.bat`・旧`scripts/deploy.ps1`等の削除 | なし（実AWSリソース・state無しを確認済み、0章） |
| Phase 2 | database構成の新規作成 | `terraform/main/database/`一式 | Phase 1 |
| Phase 3 | app構成の新規作成 | `terraform/main/app/`一式 | Phase 1（Phase 2と並行着手可、ただしapp構成側の`terraform_remote_state`定義にはPhase 2のoutputs仕様が必要） |
| Phase 4 | スクリプト再編 | `scripts/`一式（apply-database/apply-app/apply-all/destroy-database/destroy-app/seed、`common.ps1`改修） | Phase 2, 3 |
| Phase 5 | ドキュメント更新 | `terraform/README.md`の全面書き換え | Phase 4 |
| Phase 6 | 検証 | `terraform validate`/`plan`の成功確認（実AWSへの`apply`は任意・別タイミング） | Phase 5 |
| Phase 7 | 受け入れ確認 | 要件定義書14章DoDチェック結果 | Phase 6 |

## 2. WBS（作業分解構成）

| No. | タスク | Phase | 参照 | 成果物 |
|---|---|---|---|---|
| T1 | 既存`terraform/envs/`・`terraform/*.bat`・`terraform/scripts/deploy.ps1`等の削除 | 1 | 4.1節 | クリーンな`terraform/`（`bootstrap/`・`modules/`は残置） |
| T2 | `terraform/main/database/`新規作成（`backend.tf`/`variables.tf`/`main.tf`/`outputs.tf`/`terraform.tfvars.example`） | 2 | 4.2節、5.1節 | database構成一式 |
| T3 | `terraform/main/app/`新規作成（同上5ファイル） | 3 | 4.3節、5.2節 | app構成一式 |
| T4 | `modules/`配下の呼び出し元付け替え確認（モジュール自体のリソース定義は無変更） | 2, 3 | 5.3節 | 変更差分レビュー結果 |
| T5 | `scripts/common.ps1`改修（ディレクトリ変数、`Initialize-Backend`のkey引数化、`.env`読み込み拡張） | 4 | 6.1節 | `common.ps1` |
| T6 | `scripts/apply-database.ps1`/`.bat`新規作成 | 4 | 6.2節 | apply-databaseスクリプト |
| T7 | `scripts/apply-app.ps1`/`.bat`新規作成 | 4 | 6.3節 | apply-appスクリプト |
| T8 | `scripts/apply-all.ps1`/`.bat`新規作成 | 4 | 6.4節 | apply-allスクリプト |
| T9 | `scripts/destroy-database.ps1`/`.bat`新規作成 | 4 | 6.5節 | destroy-databaseスクリプト |
| T10 | `scripts/destroy-app.ps1`/`.bat`新規作成 | 4 | 6.6節 | destroy-appスクリプト |
| T11 | `scripts/seed.ps1`/`.bat`新規作成 | 4 | 6.7節 | seedスクリプト |
| T12 | `scripts/.env.example`更新（`STATE_KEY_DATABASE`/`STATE_KEY_APP`追加等） | 4 | 6.1節 | `.env.example` |
| T13 | `terraform/README.md`全面書き換え | 5 | 7章 | 新README |
| T14 | `terraform init`/`validate`/`plan`による構文・依存関係の確認 | 6 | 8章 | 検証ログ |
| T15 | 要件定義書14章DoDチェック実施 | 7 | 9章 | チェック結果 |

## 3. ディレクトリ構成（確定版）

```
terraform/
├── bootstrap/                Phase 0相当: state用S3バケット（変更なし、既存のまま）
├── main/
│   ├── database/             [database構成] ネットワーク基盤 + RDS + シード用ECS周辺リソース
│   │   ├── backend.tf
│   │   ├── variables.tf
│   │   ├── main.tf
│   │   ├── outputs.tf
│   │   └── terraform.tfvars.example
│   └── app/                  [app構成] アプリ側ECS常駐サービス周辺リソース
│       ├── backend.tf
│       ├── variables.tf
│       ├── main.tf
│       ├── outputs.tf
│       └── terraform.tfvars.example
├── modules/                   変更なし（呼び出し元のみ変更、4章参照）
│   ├── network/ / database/ / db-init-task/ / ecr/ / ecs-cluster/ / ecs-service/
│   └── service-discovery/ / mcp-inspector-task/ / cost-alert/
└── scripts/
    ├── apply-database.ps1 / apply-database.bat
    ├── apply-app.ps1 / apply-app.bat
    ├── apply-all.ps1 / apply-all.bat
    ├── destroy-database.ps1 / destroy-database.bat
    ├── destroy-app.ps1 / destroy-app.bat
    ├── seed.ps1 / seed.bat
    ├── common.ps1                （改修）
    ├── load-env.ps1              （変更なし）
    └── .env.example              （更新、6.1節）
```

`modules/database`（RDSリソース定義のモジュール）と`main/database`（database構成のroot）が同名になる点は11章オープンイシュー#2として扱う。本書の指示では改称は行わない前提で進めるが、実装担当者が混乱を感じる場合は着手前に確認すること。

## 4. Phase別作業手順

### 4.1 Phase 1: 既存構成の削除（T1）

次を削除する。

- `terraform/envs/verify-network/`、`terraform/envs/verify-database/`、`terraform/envs/verify/`（配下の`.tf`・`.tfvars.example`・`.terraform.lock.hcl`すべて）
- `terraform/deploy.bat`、`terraform/destroy.bat`、`terraform/destroy-database.bat`
- `terraform/scripts/deploy.ps1`、`terraform/scripts/destroy.ps1`、`terraform/scripts/destroy-database.ps1`

次は削除せず残す（後続Phaseで改修・更新する）。

- `terraform/bootstrap/`（無変更）
- `terraform/modules/`（無変更、4.4節参照）
- `terraform/scripts/common.ps1`、`terraform/scripts/load-env.ps1`、`terraform/scripts/.env.example`、`terraform/scripts/.env`（改修対象、Phase 4）
- `terraform/README.md`（書き換え対象、Phase 5）

実AWS上のリソース・S3上の旧state（`verify-network.tfstate`等）は存在しないことを確認済み（要件定義書13章）。そのため、AWS側の`terraform destroy`やstate移行の作業は不要であり、単純にローカルファイルを削除してよい。

### 4.2 Phase 2: database構成の新規作成（T2）

`terraform/main/database/`に次の5ファイルを作成する。詳細な変数・出力の一覧は5.1節・6.1節を参照。

- **`backend.tf`**: S3バックエンド。`bucket`・`key`・`region`はいずれも`backend.tf`内に固定値を書かず、`terraform init -backend-config=...`で注入する（6.1節）。`default_tags`に`Layer = "database"`を含める。
- **`variables.tf`**: 5.1節の変数一覧を定義する。
- **`main.tf`**: `modules/network`・`modules/database`・`modules/db-init-task`・`modules/ecr`（`db-hiroba-qa-init`用1件）を呼び出す。**重要**: 現行コードでは`network`↔`database`↔`db-init-task`は別rootのため`terraform_remote_state`で値を受け渡していたが、本再編では同一root内に統合されるため、`module.network.sg_rds_id`のように**モジュール出力を直接参照する**通常のTerraform記法に置き換える。`terraform_remote_state`はdatabase構成内では一切使用しない（app構成からdatabase構成を参照する片方向のみで使用する。6章参照）。
- **`outputs.tf`**: 5.1節の出力一覧を定義する。
- **`terraform.tfvars.example`**: 5.1節のうち`.env`経由で供給しない層固有値のみのサンプルを記載する。

### 4.3 Phase 3: app構成の新規作成（T3）

`terraform/main/app/`に次の5ファイルを作成する。詳細は5.2節・6.1節参照。

- **`backend.tf`**: S3バックエンド。database構成と同様、`bucket`/`key`/`region`は`-backend-config`で注入する。`default_tags`に`Layer = "app"`を含める。
- **`variables.tf`**: 5.2節の変数一覧を定義する。**`state_key_database`変数（database構成の出力を読むための`terraform_remote_state`用key、既定値`"database/state.tfstate"`）を新設する**点が現行構成からの変更点。
- **`main.tf`**: 冒頭で`data "terraform_remote_state" "database"`を1つだけ定義し（`bucket = var.state_bucket`、`key = var.state_key_database`、`region = var.aws_region`）、以降`local.db = data.terraform_remote_state.database.outputs`として参照する。現行コードにあった`data "terraform_remote_state" "network"`は不要になる（networkがdatabase構成に統合されたため、`local.db`経由で`sg_agent_invitro_id`等も取得する）。`modules/service-discovery`・`modules/ecs-cluster`・`modules/ecs-service`（×3）・`modules/mcp-inspector-task`・`modules/cost-alert`（条件付き）・`modules/ecr`（残り4リポジトリ）を呼び出す。
- **`outputs.tf`**: 5.2節の出力一覧を定義する。
- **`terraform.tfvars.example`**: 5.2節のうち層固有値のみのサンプルを記載する。

### 4.4 モジュール呼び出し元の付け替え確認（T4）

`modules/`配下の各モジュール自体（`network`/`database`/`db-init-task`/`ecr`/`ecs-cluster`/`ecs-service`/`service-discovery`/`mcp-inspector-task`/`cost-alert`）は、入出力インターフェースを含めて**変更しない**。今回の再編は「どのrootから何回・どの引数で呼び出すか」の変更のみであり、モジュール内部のリソース定義（`.tf`の中身）に手を加える必要はない点を実装担当者に明示する。

## 5. モジュール別・root別の変数・出力仕様

### 5.1 database構成（`terraform/main/database`）

**呼び出すモジュールと引数**

| モジュール | 主な引数の参照元 |
|---|---|
| `modules/network` | `var.vpc_id`、`var.private_subnet_ids`、`var.create_vpc_endpoints`、`var.name_prefix` |
| `modules/database` | `subnet_ids = module.network.private_subnet_ids`、`security_group_id = module.network.sg_rds_id`、`engine_version = var.rds_engine_version`、`instance_class = var.rds_instance_class`、`multi_az = var.multi_az`、`deletion_protection = var.deletion_protection`、`skip_final_snapshot = var.skip_final_snapshot` |
| `modules/ecr` | `repository_names = ["db-hiroba-qa-init"]` |
| `modules/db-init-task` | `image_uri = "${module.ecr.repository_urls["db-hiroba-qa-init"]}:${var.image_tag}"`、`secrets = { DATABASE_URL = module.database.db_url_secret_arn }`、その他環境変数は現行`envs/verify`の`db_init_task`呼び出し（`environment`ブロック）をそのまま踏襲 |

**`variables.tf`（層固有値）**

`vpc_id`、`private_subnet_ids`、`create_vpc_endpoints`、`rds_engine_version`、`rds_instance_class`、`multi_az`、`deletion_protection`（既定`true`）、`skip_final_snapshot`（既定`true`）、`image_tag`（既定`"latest"`、シード用イメージのタグ）、`csv_data_dir`、`qa_original_file`、`question_altered_file`、`category_file`、`bedrock_embedding_model_id`、`embedding_vector_dim`。加えて`aws_region`/`aws_account_id`/`name_prefix`/`state_bucket`（ADR-0038踏襲、`.env`から`TF_VAR_*`供給、tfvarsには書かない）。

**`outputs.tf`**

`vpc_id`、`private_subnet_ids`、`sg_agent_invitro_id`、`sg_tag_selector_mcp_id`、`sg_knowledge_mcp_id`、`sg_verification_task_id`、`db_url_secret_arn`、`rds_endpoint`、`rds_port`、`db_name`、`db_init_task_family`、`ecr_repository_urls`（`db-hiroba-qa-init`のみのマップ）。`sg_rds_id`は外部に出力しない（database構成内で完結するため、app構成には不要）。

### 5.2 app構成（`terraform/main/app`）

**`terraform_remote_state`定義**

```
data "terraform_remote_state" "database" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = var.state_key_database
    region = var.aws_region
  }
}
locals {
  db = data.terraform_remote_state.database.outputs
}
```

**呼び出すモジュールと引数**

| モジュール | 主な引数の参照元 |
|---|---|
| `modules/service-discovery` | `namespace_name = var.service_namespace` |
| `modules/ecs-cluster` | `cluster_name = "${var.name_prefix}-cluster"` |
| `modules/ecs-service`（`tag_selector_mcp`） | `security_group_ids = [local.db.sg_tag_selector_mcp_id]`、`subnet_ids = local.db.private_subnet_ids`、`secrets = { DATABASE_URL = local.db.db_url_secret_arn }`、その他現行`envs/verify`の定義を踏襲 |
| `modules/ecs-service`（`knowledge_mcp`） | 同上（`sg_knowledge_mcp_id`）、`desired_count = var.knowledge_mcp_desired_count` |
| `modules/ecs-service`（`agent_invitro`） | 同上（`sg_agent_invitro_id`） |
| `modules/db-init-task` | **呼び出さない**（database構成へ移設済み） |
| `modules/mcp-inspector-task` | `image_uri`、`region`のみ（SGは`local.db.sg_verification_task_id`を実行時のスクリプト側で使用。モジュール自体はSGを引数に取らない現行仕様を踏襲） |
| `modules/cost-alert` | `count = length(var.budget_alert_emails) > 0 ? 1 : 0`ほか現行`envs/verify`の定義を踏襲 |
| `modules/ecr` | `repository_names = ["knowledge-mcp", "tag-selector-mcp", "agent-invitro", "mcp-inspector"]` |

**`variables.tf`（層固有値）**

`knowledge_mcp_desired_count`（既定`1`）、`image_tag`（既定`"latest"`）、`mcp_inspector_image_tag`（既定`"latest"`）、`service_namespace`、`bedrock_chat_model_id`、`bedrock_embedding_model_id`、`embedding_vector_dim`、`bedrock_monthly_budget_usd`、`budget_alert_emails`、**`state_key_database`（新設、既定値`"database/state.tfstate"`、`.env`の`TF_VAR_state_key_database`から供給されるが、tfvarsで個別上書きも可能）**。加えて`aws_region`/`aws_account_id`/`name_prefix`/`state_bucket`（ADR-0038踏襲）。

**`outputs.tf`**

`ecr_repository_urls`（残り4リポジトリのマップ）、`cluster_name`、`mcp_inspector_task_family`、`bedrock_budget_name`。`private_subnet_ids`・`sg_verification_task_id`・`db_init_task_family`はdatabase構成側の出力（`local.db.*`）をそのまま`seed`スクリプトが`terraform output -state=...`相当で取得できるよう、app構成の`outputs.tf`にも中継出力として含めてよい（`seed`スクリプトの実装を単純化する場合の任意対応。11章オープンイシュー扱いにはしない軽微な実装判断）。

### 5.3 現行コードからの主な差分まとめ

- `envs/verify-database`にあった`data "terraform_remote_state" "network"`は、database構成では不要（モジュール直接参照に置き換え）。
- `envs/verify`にあった`data "terraform_remote_state" "network"`と`data "terraform_remote_state" "database"`（2つ）は、app構成では`data "terraform_remote_state" "database"`の1つに統合される（databaseの出力に、旧networkの出力もすべて含まれるようになるため）。
- `envs/verify`にあった`module "db_init_task"`の呼び出しは丸ごとdatabase構成へ移動する。
- `envs/verify`にあった`module "ecr"`の1回呼び出し（5リポジトリ）は、database構成（1リポジトリ）とapp構成（4リポジトリ）への2回呼び出しに分割する。

## 6. スクリプト仕様

### 6.1 `scripts/.env.example`・`common.ps1`の変更点（T5, T12）

`.env.example`に次を追加する。

| キー | 既定値 | 用途 |
|---|---|---|
| `STATE_BUCKET` | `chatbot-invitro-terraform-state-349131272460-us-east-1-an` | 両構成共通のstateバケット名（既存キー、値のみ確定） |
| `STATE_KEY_DATABASE` | `database/state.tfstate` | database構成の`-backend-config`用key。あわせて`TF_VAR_state_key_database`としてexportし、app構成の`terraform_remote_state`参照にも使う |
| `STATE_KEY_APP` | `app/state.tfstate` | app構成の`-backend-config`用key |

`common.ps1`の変更点:

- ディレクトリ変数を`NetworkDir`/`DatabaseDir`/`VerifyDir`（3つ）から`DatabaseDir`（`terraform/main/database`）・`AppDir`（`terraform/main/app`）の2つに再編する。
- `Import-Config`が`STATE_KEY_DATABASE`・`STATE_KEY_APP`を読み込み、`$script:StateKeyDatabase`・`$script:StateKeyApp`に保持する。あわせて`$env:TF_VAR_state_key_database = $script:StateKeyDatabase`をexportする（`STATE_KEY_APP`はapp構成自身の`variables.tf`では消費しないため`TF_VAR_*`化は不要、`-backend-config`用途のみでよい）。
- `Initialize-Backend`の呼び出し側（各スクリプト）で、`key`引数に`$script:StateKeyDatabase`／`$script:StateKeyApp`を渡す（現行のようなスクリプト内直書き文字列をやめる）。
- `Get-Tfvars`/`Test-Tfvars`は、対象ディレクトリ（`DatabaseDir`または`AppDir`）を引数で受け取れるよう一般化し、database構成用（`vpc_id`/`private_subnet_ids`/`rds_engine_version`等の必須チェック）とapp構成用（現行の`bedrock_chat_model_id`等の必須チェック）の両方に使えるようにする。

### 6.2 `apply-database.ps1`/`.bat`（T6）

1. `Import-Config` → `Test-Prerequisites` → database構成用`terraform.tfvars`の存在確認（無ければ雛形生成して停止）。
2. `Initialize-Backend $DatabaseDir $StateKeyDatabase $region`。
3. `terraform apply -target=module.ecr`でシード用ECRリポジトリを先行作成。
4. `db_hiroba_qa_init`イメージをdocker build/push。
5. database構成全体を`terraform apply`。
6. 単独実行を想定（app構成に影響を与えない）。

### 6.3 `apply-app.ps1`/`.bat`（T7）

1. `Import-Config` → `Test-Prerequisites` → app構成用`terraform.tfvars`の存在確認。
2. database構成が既にapply済みであることを確認する（例: `Initialize-Backend`相当の`terraform init`をdatabase構成に対して行い`terraform output`が取得できるかで判定、または単純にS3上の`database/state.tfstate`オブジェクトの存在を`aws s3api head-object`で確認する。実装方式はどちらでもよい）。未applyならエラー終了。
3. `Initialize-Backend $AppDir $StateKeyApp $region`。
4. `terraform apply -target=module.ecr`で残り4リポジトリを先行作成。
5. 4イメージをdocker build/push。
6. app構成全体を`terraform apply -var "knowledge_mcp_desired_count=<呼び出し元指定、既定1>"`。
7. 単独実行を想定（RDS・ネットワークには影響しない）。

### 6.4 `apply-all.ps1`/`.bat`（T8）

1. Phase 0相当: `bootstrap`のstateバケット未作成なら作成（`state_bucket_name = $StateBucket`）。
2. `apply-database`相当の処理を実行。
3. `apply-app`相当の処理を`knowledge_mcp_desired_count=0`で実行。
4. `seed`相当の処理を実行し、`exitCode=0`を確認する。
5. `apply-app`相当の処理を`knowledge_mcp_desired_count=1`で再実行（ゲート解放）。
6. 全体実行前に課金リソース作成の確認プロンプトを表示（`-AutoApprove`で省略可）。
7. MCP Inspector等の手動検証は対象外（README側の手順に委ねる）。

### 6.5 `destroy-database.ps1`/`.bat`（T9）

1. 警告文（RDS・投入済みデータが完全消失し、再構築には再シードが必要になる旨）を表示。
2. `destroy-database`という文字列入力によるタイプ確認。
3. app構成が残っている場合の警告表示（11章オープンイシュー#4: 自動検出して停止するレベルまで実装するかは実装時判断。最低限、警告メッセージの表示は必須要件とする）。
4. `Initialize-Backend $DatabaseDir $StateKeyDatabase $region`。
5. `terraform apply -var deletion_protection=false`で削除保護解除。
6. `terraform destroy -var deletion_protection=false -var skip_final_snapshot=true`。

### 6.6 `destroy-app.ps1`/`.bat`（T10）

1. `destroy-app`という文字列入力によるタイプ確認（`destroy-database`ほど厳重でなくてよい）。
2. `Initialize-Backend $AppDir $StateKeyApp $region`。
3. `terraform destroy`。
4. RDS（database構成）は残る旨、再開時は`apply-app`のみでよい旨をメッセージ表示。

### 6.7 `seed.ps1`/`.bat`（T11）

1. database構成・app構成の両方が既にapply済みであることを前提とする。
2. `Initialize-Backend`でdatabase構成・app構成それぞれに`terraform init`（출力取得のため）。
3. app構成から`cluster_name`を、database構成から`private_subnet_ids`・`sg_verification_task_id`・`db_init_task_family`を`terraform output`で取得する。
4. `aws ecs run-task`でシードタスクを起動し、`STOPPED`になるまでポーリング、`exitCode=0`を確認する（タイムアウト・異常終了時はCloudWatch Logsのロググループ名を含むエラーメッセージで停止）。
5. `apply-all`から呼び出されるほか、単独実行も可能とする（再シード用途）。

## 7. `terraform/README.md`の更新方針（T13）

現行README（3層構成の説明・実行手順）を、次の構成に合わせて全面的に書き換える。

- ディレクトリ構成図を8章相当（本書3章）の新構成に更新する。
- 「かんたん実行（bat）」節を、`apply-database.bat`/`apply-app.bat`/`apply-all.bat`/`destroy-database.bat`/`destroy-app.bat`/`seed.bat`の6本立てに更新する。
- 「実行手順（Phase別）」節を、Phase 1（database構成）→ Phase 2（app構成のECR+イメージ）→ Phase 3（app構成apply、ゲート閉）→ Phase 4（シード）→ Phase 5（app構成再apply、ゲート開放）→ Phase 6（手動検証）という2層構成向けの手順に書き換える。
- 「注意点」節のうち、DB永続化・destroy対象範囲・ECS Exec事後有効化不可・pgvectorバージョン要再確認・Service Connectタイムアウト・DATABASE_URL・CSVデータ同梱に関する既存の注意書きは、database構成/app構成の呼称に置き換えつつ内容自体は維持する。

## 8. 検証・テスト指示（T14）

- database構成・app構成それぞれのディレクトリで`terraform init`（`-backend-config`に6.1節の値を使用）→ `terraform validate`が構文エラーなく完了することを確認する。
- `terraform.tfvars`にプレースホルダではない値（少なくとも構文的に妥当な値。実在のVPC ID等は未確定でもよいが、実装時点で判明していれば実値を使う）を設定し、`terraform plan`がエラーなく完了すること（AWS認証情報が必要）を確認する。
- 実際のAWSへの`apply`（実リソース作成）は、本書のスコープでは必須としない。実施する場合は、利用者から実際の`vpc_id`/`private_subnet_ids`等の受領後、`apply-all`を用いて行う。

## 9. 完了条件（要件定義書14章のDoDに対応する実装レベルの確認項目）

- [ ] `terraform/`配下が3章のディレクトリ構成になっている。
- [ ] database構成・app構成の`terraform validate`が成功する。
- [ ] `apply-database`/`apply-app`/`apply-all`/`destroy-database`/`destroy-app`/`seed`の6スクリプト（`.ps1`+`.bat`）が揃っている。
- [ ] `.env.example`に`STATE_KEY_DATABASE`/`STATE_KEY_APP`が追加され、バケット名・keyのハードコードが`.tf`/`.ps1`のいずれにも存在しない。
- [ ] database構成のみに`terraform_remote_state`が存在しない（app構成からの片方向参照のみ）ことをコードレビューで確認する。
- [ ] `terraform/README.md`が新構成に合わせて更新されている。
- [ ] 旧`envs/verify-network`・`envs/verify-database`・`envs/verify`・旧`*.bat`・旧`deploy.ps1`等が削除されている。

## 10. 実装時の注意点・落とし穴

- **backendブロックは変数を参照できない**: `bucket`/`key`/`region`を`backend.tf`に直書きせず、必ず`-backend-config`で渡すこと。うっかり`key = "database/state.tfstate"`のような固定値を書いてしまうと、`.env`側で値を変えても反映されない（`-reconfigure`を付けない限り古い値がstateファイルの参照に残り続ける事故にもつながる）。
- **database構成内は`terraform_remote_state`を使わない**: network/database/db-init-taskが同一rootに統合されたため、モジュール間の値の受け渡しは通常のモジュール出力参照（`module.network.xxx`）で完結する。誤って旧コードの`terraform_remote_state`ブロックをそのまま残さないよう注意する。
- **destroy順序**: app構成を先に`destroy-app`し、その後`destroy-database`を実行する。逆順で行うと、app構成のECSサービスがdatabase構成のセキュリティグループ・サブネットを使用中のため、AWS側の依存関係違反で`destroy-database`が失敗する可能性がある（ADR-0039参照）。
- **RDSの`deletion_protection`既定`true`**: `destroy-database`は保護解除→destroyの2段階が必須。1段階だけで済ませようとするとエラーになる。
- **`modules/database`と`main/database`の名称類似**: ログやエラーメッセージで混同しないよう、実装担当者間で呼称（「dbモジュール」「database root」等）を揃えておくこと。
- **ECS Execは事後有効化不可**（既存の注意点を継承）: `agent_invitro`・検証用タスクでは最初から`enable_execute_command = true`にしておくこと。
- **pgvector対応エンジンバージョン**（既存の注意点を継承）: 実装時にAWS公式情報で再確認すること。
- **今回は「移行」ではなく「新規作成」**: 実AWS環境・S3上の旧stateは存在しない前提のため、`terraform state mv`やインポート作業は不要。誤ってそのような手順を追加しないこと。

## 11. Open Issues（実装時に確定が必要な事項）

要件定義書15章から引き継ぐ、残る5件。実装着手のブロッカーではないが、実装完了までに確定させること。

1. **ECRモジュールの分割方法**（5.3節）: `module.ecr`をdatabase構成・app構成で2回呼び出す方針でよいか。
2. **`modules/database`と`main/database`の名称重複**: 混同のリスクが実務上問題になる場合、`modules/database`を`modules/rds`等に改称するか。改称する場合は本書のモジュール参照箇所もあわせて修正が必要。
3. **`modules/mcp-inspector-task`の帰属**: app構成を既定としているが、シード検証系としてdatabase構成にまとめる案も残っている。
4. **`destroy-database`の安全ガード実装レベル**（6.5節）: app構成が残っている場合の自動検出・強制停止まで実装するか、警告メッセージ表示に留めるか。
5. **将来の複数環境対応**: 本番相当の環境を追加する場合の`terraform/main/`配下の拡張方針（`<env>-database`/`<env>-app`か、環境ごと`main-<env>/`で分けるか）。今回は設計のみで実装対象外。

## 12. 実装着手前に確認をお願いしたい事項（再掲）

0章の内容（ディレクトリ名、stateバケット名・key、cost-alertの帰属、既存AWS環境の状況）は、いずれも利用者により確認済みであり、実装着手可能な状態にある。11章の残る5件は、実装を進めながら並行して確定してよい（着手をブロックしない）。

実装着手前に改めて確認しておきたい点は次の1つのみ。

- 本書は「Terraformコード自体の実装」を含まない要件・仕様の指示書である。実際の`.tf`/`.ps1`/`.bat`ファイルの作成は、本書を入力として別途のコーディング作業（本セッションのスコープ外）で行うこと。
