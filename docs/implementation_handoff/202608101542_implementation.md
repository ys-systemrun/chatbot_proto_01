# MCPサーバー・クライアント AWS デプロイ 実装指示書

- 文書番号: IMPL-202608101542
- 対象プロジェクト: chatbot_invitro
- 参照文書:
  - 要件定義書 `docs/requirement/202608100910_MCPサーバークライアントAWSデプロイ要件定義書.md`（REQ-202608100910、ステータス: Confirmed）
  - ADR `docs/adr/0023〜0030`（本デプロイのために新設）
  - 関連（既存）: ADR-0002, 0003, 0007（Knowledge/Tag Selector MCPの実行形態・ベクトルストア方針）、ADR-0016〜0018（`db_hiroba_qa_init`のマイグレーション・シード方針）、ADR-0019〜0022（`agent_invitro`の設計）
- 対象コンポーネント: `terraform/`（新規）、`knowledge_mcp`・`tag_selector_mcp`・`agent_invitro`・`db_hiroba_qa_init`（いずれもDockerイメージのビルド・ECRプッシュ対象。アプリケーションコード自体への変更は本書の対象外）
- 本書の位置づけ: 要件定義書・ADRで確定した方針を、実装担当者（インフラ担当者またはコーディングエージェント）が着手できる粒度まで具体化した指示書である。本書自体はTerraformコード・アプリケーションコードを含まない（リソース仕様・作業手順・設定値の指示にとどめる）。実際の`.tf`ファイル作成・アプリケーション変更は別途担当者が本書の指示に従って行うこと。

## 0. 本書作成にあたり確定した事項

要件定義書のOpen Issuesのうち、実装着手には確定が必要だが未決だった項目、および本書作成にあたり補足した項目を以下に整理する。

| 項目 | 決定内容 | 根拠・備考 |
|---|---|---|
| アクセス範囲 | AWS内部限定。外部公開・オンプレ直接接続なし | 発注者確認済み、ADR-0023 |
| コンピュート基盤 | ECS Fargate（4コンポーネントすべて） | 発注者確認済み、ADR-0024 |
| `agent_invitro`の実行形態 | ECS Fargate常駐サービス化。動作確認はECS Exec | 発注者確認済み、ADR-0025 |
| DB配置 | Amazon RDS for PostgreSQL（pgvector拡張）へ移行 | 発注者確認済み、ADR-0026 |
| アプリケーションレベル認証 | 差し当たり実装しない | 発注者確認済み、ADR-0023追記 |
| Terraform state管理 | S3バックエンド | 発注者確認済み、ADR-0027 |
| 環境固有設定（アカウントID・リージョン等） | Git管理外の`terraform.tfvars` | 発注者確認済み、ADR-0028 |
| MCP Inspectorによる検証 | ECS Execで一時起動した検証用タスクから実行 | 発注者確認済み、ADR-0029 |
| `db_hiroba_qa_init`のAWS展開 | ECR + ECS Run Task方式でRDSへマイグレーション・シード | 発注者確認済み、ADR-0030 |
| ECRリポジトリの要否（本書での補足） | 4コンポーネントすべてにECRリポジトリが必要（ECS FargateはECR等のレジストリからのイメージ取得を前提とするため） | **本書での補足**（ADR-0030の結果・影響を踏まえ、全コンポーネント共通の前提として明示） |

残るOpen Issueは次の1点であり、これは本書・要件定義書のいずれでも決定できない、発注者側の環境情報である。

- **AWSアカウントID・リージョンの具体的な値**（要件定義書 Open Issue #6）: 実装着手前（4章のブートストラップ作業前）に発注者から受領し、`terraform.tfvars`に設定すること。値が確定するまで、Phase 1以降（実際のリソース作成）には着手できない。

## 1. 全体進行フェーズ

| Phase | 目的 | 主な成果物 | 前提 |
|---|---|---|---|
| Phase 0 | ブートストラップ | state用S3バケット、ECRリポジトリ×4、`terraform.tfvars`（実値） | AWSアカウントID・リージョンの受領（0節） |
| Phase 1 | ネットワーク基盤 | VPC、プライベートサブネット、セキュリティグループ | Phase 0 |
| Phase 2 | データベース | RDSインスタンス（pgvector拡張） | Phase 1 |
| Phase 3 | コンテナイメージ | 4コンポーネントのDockerイメージビルド・ECRプッシュ | Phase 0 |
| Phase 4 | データ投入 | `db_hiroba_qa_init` Run Task実行、RDSへのマイグレーション・シード完了 | Phase 2, 3 |
| Phase 5 | アプリケーション基盤 | `tag_selector_mcp`・`knowledge_mcp`・`agent_invitro`のECS Fargateサービス起動 | Phase 4（`knowledge_mcp`はPhase 4完了後に起動） |
| Phase 6 | 動作検証 | MCP Inspectorによるプロトコル層検証、手動テストクエリによるクライアント統合層検証 | Phase 5 |
| Phase 7 | 受け入れ確認 | 要件定義書12章DoDチェック結果、ドキュメント更新 | Phase 6 |

Phase 4（データ投入）は、`knowledge_mcp`起動より前に完了させること（6.7〜6.8節、ADR-0018の起動順序制御の考え方を踏襲）。ECSにはdocker-composeの`depends_on: condition: service_completed_successfully`に相当する自動待機機能がないため、Phase 4→Phase 5の順序はデプロイ手順（本書7章）側で担保する。

## 2. WBS（作業分解構成）

| No. | タスク | Phase | 参照 | 成果物 |
|---|---|---|---|---|
| T1 | AWSアカウントID・リージョンの受領、`terraform.tfvars`作成（`.gitignore`対象） | 0 | 0節、ADR-0028 | `terraform.tfvars`（非公開） |
| T2 | Terraform state用S3バケットの作成（バージョニング・暗号化有効化） | 0 | ADR-0027 | S3バケット |
| T3 | ECRリポジトリ×4の作成 | 0 | ADR-0030 | ECRリポジトリ |
| T4 | `network`モジュール実装指示（VPC・サブネット・セキュリティグループ） | 1 | 5.1節、ADR-0023 | `modules/network` |
| T5 | `database`モジュール実装指示（RDS、pgvector） | 2 | 5.3節、ADR-0026 | `modules/database` |
| T6 | 4コンポーネントのDockerイメージビルド・ECRプッシュ手順 | 3 | 5.2節 | ECR上のイメージ |
| T7 | `db-init-task`モジュール実装指示（`db_hiroba_qa_init`のRun Task定義） | 4 | 5.6節、ADR-0030 | `modules/db-init-task` |
| T8 | `db_hiroba_qa_init`タスクの実行・完了確認 | 4 | 8.1節 | 実行結果ログ |
| T9 | `ecs-cluster`モジュール実装指示 | 5 | 5.4節、ADR-0024 | `modules/ecs-cluster` |
| T10 | `ecs-service`モジュール実装指示（3コンポーネント共通） | 5 | 5.5節、ADR-0024, 0025 | `modules/ecs-service` |
| T11 | `service-discovery`モジュール実装指示（ECS Service Connect） | 5 | 6.2節（要件定義書） | `modules/service-discovery` |
| T12 | `mcp-inspector-task`モジュール実装指示 | 6 | 5.7節、ADR-0029 | `modules/mcp-inspector-task` |
| T13 | プロトコル層検証（MCP Inspector）の実施 | 6 | 8.2節 | 検証結果ログ |
| T14 | クライアント統合層検証（手動テストクエリ）の実施 | 6 | 8.3節 | 検証結果ログ |
| T15 | DoDチェックリスト実施 | 7 | 9章 | チェック結果 |

## 3. Terraformディレクトリ・モジュール構成（確定版）

```
terraform/
├── bootstrap/                    … Phase 0専用の最小構成（state用バケット自体はメイン構成の外で管理、7.1節）
│   └── main.tf                    （S3バケット・必要であればDynamoDBテーブルのみを定義）
├── envs/
│   └── verify/
│       ├── main.tf                 … 各モジュールの呼び出し
│       ├── variables.tf
│       ├── outputs.tf
│       ├── backend.tf              … S3バックエンド設定（ADR-0027）
│       └── terraform.tfvars.example  … 変数キーのサンプル（実体はGit管理外、ADR-0028）
├── modules/
│   ├── network/                    … VPC・プライベートサブネット・セキュリティグループ（5.1節）
│   ├── ecr/                        … 4コンポーネント分のECRリポジトリ（5.2節）
│   ├── database/                   … RDS for PostgreSQL（pgvector拡張）、DBサブネットグループ（5.3節）
│   ├── ecs-cluster/                 … ECS Fargateクラスタ共通部分（5.4節）
│   ├── ecs-service/                 … 常駐サービス共通モジュール（tag_selector_mcp/knowledge_mcp/agent_invitroで3回呼び出す、5.5節）
│   ├── db-init-task/                 … db_hiroba_qa_init用Run Taskタスク定義（5.6節）
│   ├── service-discovery/            … ECS Service Connectの設定（5.5節に含める形でもよい）
│   └── mcp-inspector-task/           … MCP Inspector検証用の一時タスク定義（5.7節）
└── README.md                        … 本書4〜8章の作業手順の要約、実行者向け
```

## 4. Phase 0: ブートストラップ作業手順（T1〜T3）

1. **AWSアカウントID・リージョンの受領**（T1）: 発注者から実際の値を受領し、`terraform.tfvars`（`.gitignore`対象）に設定する。値を受領するまで本章以降には着手しない。
2. **`.gitignore`の更新**: `terraform.tfvars`（サンプルの`terraform.tfvars.example`を除く`*.tfvars`）、`*.tfstate`、`*.tfstate.backup`、`.terraform/`を追加する。
3. **state用S3バケットの作成**（T2）: `terraform/bootstrap/`配下に、メイン構成とは別の最小限のTerraform構成（またはAWS CLI/コンソールでの手動作成）でS3バケットを作成する。バージョニング・サーバーサイド暗号化（SSE-S3またはSSE-KMS）を有効化する（ADR-0027）。ロック方式は、利用するTerraformのバージョンが1.10以上であればS3ネイティブロック（`use_lockfile = true`）を、それ未満であればDynamoDBロックテーブルを別途作成する。
4. **ECRリポジトリ×4の作成**（T3）: `knowledge-mcp`・`tag-selector-mcp`・`agent-invitro`・`db-hiroba-qa-init`の4リポジトリを作成する（`modules/ecr`で管理してよい。ブートストラップと本編どちらで管理するかは実装時の判断でよいが、循環依存を避けるため、少なくともメイン構成の`terraform apply`より前にリポジトリ自体は存在している必要がある）。イメージスキャン（push時の脆弱性スキャン）の有効化を推奨する。

## 5. モジュール別リソース仕様

### 5.1 `network`モジュール（T4、ADR-0023）

| リソース | 仕様 |
|---|---|
| VPC | CIDRは`terraform.tfvars`で指定（例: `10.20.0.0/16`、実値は実装時に確定） |
| プライベートサブネット | 2つ以上のAZに分散配置（将来のRDS Multi-AZ化に備える）。パブリックサブネット・インターネットゲートウェイは作成しない（ADR-0023） |
| NATゲートウェイ（任意） | 外部LLM API（OpenAI等）を利用する場合のみ作成し、アウトバウンド通信専用とする。Bedrockのみ利用する場合はVPCエンドポイント（Interface型）で代替可能 |
| セキュリティグループ | `sg-agent-invitro`（送信専用）、`sg-tag-selector-mcp`（`sg-agent-invitro`からのインバウンドのみ許可）、`sg-knowledge-mcp`（`sg-agent-invitro`からのインバウンドのみ許可）、`sg-rds`（`sg-knowledge-mcp`・`sg-db-init-task`からのインバウンドのみ許可、5432番ポート）、`sg-verification-task`（MCP Inspector検証用タスク・`db_hiroba_qa_init`共用可、アウトバウンドは`sg-tag-selector-mcp`/`sg-knowledge-mcp`/`sg-rds`宛のみ） |

主要な許可ルール一覧（要件定義書6.3節・6.7節の実装レベル対応表）:

| From | To | Port | 用途 |
|---|---|---|---|
| `sg-agent-invitro` | `sg-tag-selector-mcp` | MCPポート（例: 8200） | `select_tags`呼び出し |
| `sg-agent-invitro` | `sg-knowledge-mcp` | MCPポート（例: 8100） | `search_knowledge`呼び出し |
| `sg-knowledge-mcp` | `sg-rds` | 5432 | 通常のクエリ |
| `sg-verification-task` | `sg-rds` | 5432 | `db_hiroba_qa_init`のマイグレーション・シード実行（ADR-0030） |
| `sg-verification-task` | `sg-tag-selector-mcp` / `sg-knowledge-mcp` | MCPポート | MCP Inspectorによる検証（ADR-0029） |

上記以外のインバウンドはすべて拒否する。9.1節の否定的検証で、このルール以外の経路が実際に遮断されることを確認する。

### 5.2 `ecr`モジュール（T3、T6）

- 4リポジトリ（`knowledge-mcp`、`tag-selector-mcp`、`agent-invitro`、`db-hiroba-qa-init`）を作成する。
- イメージのビルド・プッシュ手順（T6、実装担当者が実施）: 各コンポーネントの既存`Dockerfile`をそのまま利用し、`docker build` → `docker tag` → `aws ecr get-login-password`によるログイン → `docker push`という標準的な手順を用いる。アプリケーションコード自体の変更は不要（要件定義書11章）。
- イメージタグ運用（例: `latest`固定か、コミットハッシュ/日付タグを使うか）は実装時に確定してよいが、再現性のため`latest`のみに頼らずタグを明示することを推奨する。

### 5.3 `database`モジュール（T5、ADR-0026）

| 項目 | 仕様（提案値、実装時に確定） |
|---|---|
| エンジン | Amazon RDS for PostgreSQL |
| エンジンバージョン | pgvector拡張が利用可能な最小バージョン以上。**実装時にAWS公式ドキュメントで対応バージョンを再確認すること**（本書作成時点の情報が古くなっている可能性があるため） |
| インスタンスクラス | 検証用途のため最小クラス（例: `db.t3.micro`または`db.t4g.micro`）を初期値とし、性能問題があれば見直す |
| Multi-AZ | 無効（要件定義書8章、検証用途のため） |
| ストレージ | 汎用SSD（gp3）、最小サイズから開始 |
| DBサブネットグループ | 5.1節のプライベートサブネットを使用 |
| セキュリティグループ | `sg-rds`（5.1節） |
| 認証情報 | RDSのマスターパスワード自動生成 + AWS Secrets Manager統合機能を利用し、`knowledge_mcp`・`db_hiroba_qa_init`のタスク定義から`secrets`参照で注入する（要件定義書6.6節・6.7節） |
| pgvector拡張の有効化 | RDSのパラメータグループで`vector`拡張が許可リストに含まれることを確認したうえで、`db_hiroba_qa_init`の既存マイグレーション（`CREATE EXTENSION IF NOT EXISTS vector;`を含む、ADR-0017）で有効化する。アプリケーション側の変更は不要 |
| 削除保護 | 検証用途のため無効化を推奨（`terraform destroy`でのクリーンな削除を優先）。ただし投入したデータを誤って失う運用にならないよう、実施者間で認識を合わせること |

### 5.4 `ecs-cluster`モジュール（T9、ADR-0024）

- ECS Fargate用のクラスタを1つ作成する。Container Insightsの有効化を推奨（CloudWatchでの可視性向上、要件定義書8章）。

### 5.5 `ecs-service`モジュール（T10・T11、ADR-0024, 0025）

`tag_selector_mcp`・`knowledge_mcp`・`agent_invitro`の3コンポーネントに対して共通モジュールとして3回呼び出す。

| 入力変数 | 説明 |
|---|---|
| `service_name` | ECSサービス名（Service Connect名としても使用、例: `tag_selector_mcp`、`knowledge_mcp`） |
| `image_uri` | 5.2節のECRリポジトリのイメージURI |
| `cpu` / `memory` | Fargateタスクサイズ（初期値は既存ローカル環境のリソース使用感を踏まえて実装時に決定） |
| `container_port` | 各コンポーネントの既存ポート（`tag_selector_mcp`: 8200、`knowledge_mcp`: 8100。`agent_invitro`は常駐だが外部公開ポートなし、ADR-0025） |
| `environment` | 環境変数マップ（6章参照） |
| `secrets` | Secrets Manager参照（DB認証情報、外部LLM APIキー等） |
| `security_group_id` | 5.1節の対応するセキュリティグループ |
| `enable_execute_command` | `agent_invitro`では`true`固定（ADR-0025、ECS Exec前提）。`tag_selector_mcp`・`knowledge_mcp`も検証用に`true`を推奨 |
| `service_connect_configuration` | ECS Service Connectで名前解決を有効化（要件定義書6.2節、docker-composeの内部DNS名に相当） |

`agent_invitro`固有の注意: ADR-0025により常駐サービス化するが、外部からのリクエストを受け付けるAPIとしては公開しない（コンテナポートの用途はECS Exec接続のみ）。既存のローカル実行形態（`tty: true` + `sleep infinity`相当のプロセス維持、`docker compose exec ... ipython`）を、ECS Fargateのタスク定義でも同様に維持する必要がある（コンテナのメインプロセスが終了しないようにする）。

### 5.6 `db-init-task`モジュール（T7、ADR-0030）

- `db_hiroba_qa_init`用のECSタスク定義のみを作成し、**常駐サービスは作成しない**。
- 実行は`aws ecs run-task`をPhase 4（T8）で都度呼び出す運用とする。
- `enable_execute_command`は必須ではないが、トラブルシュート用に`true`を推奨。
- セキュリティグループは`sg-verification-task`（5.1節）を使用し、RDSへの到達性のみを持たせる。
- 環境変数は既存のローカル環境（`docker-compose.yml`の`db_hiroba_qa_init`定義）と同等の項目（`DATABASE_URL`相当、`EMBEDDING_VECTOR_DIM`、`CSV_DATA_DIR`等）をECS側の環境変数・Secrets参照に置き換える。

### 5.7 `mcp-inspector-task`モジュール（T12、ADR-0029）

- MCP Inspector（Node.js CLIツール）をインストールしたDockerイメージを別途用意し、ECRにプッシュする（既存4コンポーネントとは別の、検証専用の新規イメージ）。
- `db-init-task`と同様、常駐サービスは作成せず、必要な時に`aws ecs run-task`で起動し、ECS Execで接続して使う。
- セキュリティグループは`sg-verification-task`（`tag_selector_mcp`・`knowledge_mcp`への到達性のみ）を使用する。

## 6. 環境変数・tfvars一覧（確定表）

### 6.1 `terraform.tfvars`（Terraform変数、Git管理外、ADR-0028）

| 変数名 | 説明 |
|---|---|
| `aws_account_id` | デプロイ先AWSアカウントID（発注者から受領、Open Issue #6） |
| `aws_region` | デプロイ先リージョン（発注者から受領、Open Issue #6） |
| `vpc_cidr` | VPCのCIDRブロック |
| `availability_zones` | 使用するAZのリスト |
| `rds_instance_class` | RDSインスタンスクラス（5.3節） |
| `rds_engine_version` | RDSエンジンバージョン（5.3節、実装時に確認） |

### 6.2 ECSタスクの環境変数（既存の`.env`/`docker-compose.yml`からの引き継ぎ）

| 変数名 | AWS環境での値の変更点 |
|---|---|
| `KNOWLEDGE_MCP_URL` | docker-compose内部DNSからECS Service Connect名（例: `http://knowledge_mcp:8100/mcp`）へ。ポート番号・パスは既存を踏襲 |
| `TAG_SELECTOR_MCP_URL` | 同上（`http://tag_selector_mcp:8200/mcp`） |
| `DATABASE_URL`相当（`knowledge_mcp`・`db_hiroba_qa_init`） | RDSのエンドポイントに変更。認証情報はSecrets Manager参照に変更（平文の環境変数としては注入しない） |
| `LLM_PROVIDER` / `LMSTUDIO_CHAT_URL`等 | **AWS環境ではAmazon Bedrockへ切り替えることが確定した（発注者確認済み、ADR-0031）。** `LLM_PROVIDER=bedrock`相当の値、利用するBedrockモデルID（チャット用・エンベディング用）、リージョン等に置き換える。ECSタスクロールにBedrock呼び出し権限（`bedrock:InvokeModel`等）を付与し、APIキーは使用しない |
| `EMBEDDING_VECTOR_DIM` | Bedrockの埋め込みモデル（Titan Text Embeddings V2、Cohere Embed Multilingual等）の出力次元に合わせて値を設定する（ADR-0031、ADR-0017のパラメータ化の仕組みをそのまま利用） |

`LMSTUDIO_*`系の変数は、AWS環境ではBedrock向けの変数（モデルID等）に置き換える。ただし**この置き換えに対応するアプリケーションコードの変更（`tag_selector_mcp`・`agent_invitro`のLLM呼び出し部分、`db_hiroba_qa_init`のエンベディング呼び出し部分）は本書のスコープ外**であり、別途コーディング担当向けの実装指示を整理する必要がある（12章参照）。ローカル開発環境（docker-compose、LM Studio）の`.env`/`docker-compose.yml`自体には変更を加えない（ADR-0031、ローカル開発フローへの影響なし）。

## 7. 実装順序と依存関係

1. **T1〜T3（Phase 0）**を最初に完了させる。AWSアカウントID・リージョンが未受領の場合、後続作業に着手しない。
2. **T4（network）**を適用する。
3. **T5（database）**・**T6（イメージビルド・プッシュ）**はT4完了後、並行して進めてよい。
4. **T7（db-init-taskモジュール）**はT4・T5・T6（`db-hiroba-qa-init`イメージ）完了後に適用する。
5. **T8（db_hiroba_qa_initの実行）**はT7完了後に実施し、正常終了を確認する（8.1節）。**T8の完了を確認するまで、次のT10（`knowledge_mcp`サービス起動）には進まないこと。**
6. **T9（ecs-cluster）**はT4と並行して進めてよい。
7. **T10・T11（ecs-service、service-discovery）**は、T6（`tag_selector_mcp`・`knowledge_mcp`・`agent_invitro`のイメージ）・T8（データ投入完了）・T9完了後に適用する。`tag_selector_mcp`は`knowledge_mcp`のデータに依存しないため、T8を待たずに起動してよい。
8. **T12（mcp-inspector-task）**はT4完了後、いつでも適用可能（常駐しないため他タスクとの依存は薄い）。
9. **T13・T14（Phase 6検証）**はT10・T11完了後に実施する。
10. **T15（DoD確認）**は全工程完了後に実施する。

## 8. テスト・検証指示（Phase 6〜7、T8・T13・T14）

### 8.1 `db_hiroba_qa_init`の実行確認（T8）

- `aws ecs run-task`で`db-init-task`を起動し、CloudWatch Logsでマイグレーション・シードのログを確認する。
- タスクの終了コードが0であることを確認する（`aws ecs describe-tasks`の`containers[].exitCode`）。
- RDSに接続し（`db-init-task`用の一時的な踏み台、または同一タスク定義を流用した確認用の一時起動で）、想定したQA・タグデータが投入されていることを確認する。

### 8.2 プロトコル層の検証（T13、ADR-0029）

- `aws ecs run-task`で`mcp-inspector-task`を起動する。
- ECS Exec（`aws ecs execute-command --command "/bin/sh" --interactive`）でタスクに接続する。
- MCP Inspectorから、Service Connect名経由で`tag_selector_mcp`・`knowledge_mcp`それぞれに対し`tools/list`・`tools/call`を実行し、ローカル環境と同様の応答が得られることを確認する。
- 確認後、`aws ecs stop-task`でタスクを停止する。

### 8.3 クライアント統合層の検証（T14）

- `agent_invitro`のECSタスクに対し、ECS Exec（`aws ecs execute-command --command "ipython" --interactive`、ADR-0025）で接続する。
- 要件定義書・会話エージェント実験要件定義書（`202608061621.md`）6.4節の手動テストクエリ（3件）を実行する。
- CloudWatch Logsで、`select_tags` → `search_knowledge`の順にツールが呼び出されていること、最終回答が生成されていることを確認する。

### 8.4 否定的アクセス検証（9.1節、5.1節のセキュリティグループ表に対応）

- 許可されていない経路（例: `sg-agent-invitro`以外から`sg-knowledge-mcp`への到達、VPC外からの到達）を、一時的な検証用リソースを使って試行し、到達できないことを確認する。

## 9. 完了条件（要件定義書12章のDoDに対応する実装レベルの確認項目）

- [ ] `terraform apply`（`envs/verify`）が正常終了し、VPC・RDS・ECSクラスタ・4コンポーネント分のタスク定義/サービスが作成される。
- [ ] `db_hiroba_qa_init`のRun Taskが正常終了し、RDSに検証用データが投入されている（8.1節）。
- [ ] `tag_selector_mcp`・`knowledge_mcp`・`agent_invitro`の3サービスが起動し、ヘルスチェックがPassingになる。
- [ ] 8.4節の否定的アクセス検証で、意図しない経路からの到達ができないことを確認できる。
- [ ] MCP Inspectorから両MCPサーバーへの`tools/list`・`tools/call`が成功する（8.2節）。
- [ ] `agent_invitro`から手動テストクエリを実行し、期待されるツール呼び出し順序・最終回答が得られる（8.3節）。
- [ ] 検証終了後、`terraform destroy`でリソース（RDSを含む）を破棄できる。

## 10. 実装時の注意点・落とし穴

- **Terraform stateバックエンドの循環依存**: state用S3バケット自体をメイン構成（`envs/verify`）のTerraformで管理すると、初回`terraform init`時にバックエンドが存在しないという循環が生じる。4章の通り、`terraform/bootstrap/`で別途管理するか、手動作成すること。
- **ECS Execは事後有効化できない**: `enableExecuteCommand`はタスク定義・サービス作成時に設定する必要があり、既存の起動済みサービスに後から有効化する場合はサービスの再作成（強制デプロイ）が必要になる。`agent_invitro`・検証用タスクでは最初から有効化しておくこと（ADR-0025, 0029）。
- **RDSのpgvector拡張対応バージョン**: 本書作成時点の情報が古くなっている可能性があるため、実装着手時にAWS公式ドキュメントで、選定するPostgreSQLエンジンバージョンがpgvector拡張に対応していることを必ず確認すること（5.3節）。
- **ECS Service Connectのタイムアウト設定**: Streamable HTTP（SSEベース）のような長時間コネクションを使う場合、Service Connect（Envoyプロキシ）側のタイムアウト設定がデフォルトのままでは短すぎる可能性がある。既存のローカルdocker-compose環境では発生しなかった問題のため、AWS環境特有の検証項目として8.2節・8.3節の検証時に併せて確認すること。
- **`db_hiroba_qa_init`実行順序の手動担保**: 7章5点目の通り、ECSにはdocker-composeの`depends_on: condition: service_completed_successfully`に相当する自動待機機能がない。CI/CD導入時（本書スコープ外）は、この順序制御をパイプラインのステップとして明示的に組み込む必要がある。
- ~~**LM Studio（ローカルLLM）への到達性**~~ → 発注者確認の結果、AWS環境のチャット・エンベディング用LLMはAmazon Bedrockへ切り替えることが確定した（ADR-0031）。これに伴い、`tag_selector_mcp`・`agent_invitro`・`db_hiroba_qa_init`のLLM呼び出し部分のアプリケーションコード変更が新たに必要になるが、これは本書（インフラ構築指示）のスコープ外であり、別途コーディング担当向けの実装指示が必要になる（12章）。Bedrockのモデルアクセスは、AWSアカウント・リージョンごとに有効化申請が必要な場合があるため、実装着手時にAWSコンソールで確認すること。
- **コスト管理**: ECS Fargate・RDSは常時起動するとコストが発生し続ける。検証終了後は速やかに`terraform destroy`を実施する運用ルールを徹底すること。

## 11. Open Issues（実装時に確定が必要な事項）

1. **AWSアカウントID・リージョンの実値**（要件定義書 Open Issue #6）: 発注者から受領し、`terraform.tfvars`に設定する。
2. ~~**エージェント用LLM接続先のAWS環境での扱い**~~ → 発注者確認の結果、Amazon Bedrockへ切り替えることが確定した（ADR-0031）。対応するアプリケーションコードの変更は、実装指示書`docs/implementation_handoff/202608101616_implementation.md`（IMPL-202608101616）として別途整理済み。
3. **RDSインスタンスクラス・pgvector対応エンジンバージョンの確定値**（5.3節）: 実装時にAWS公式情報を確認のうえ確定する。
4. **ECS Fargateタスクサイズ（CPU/メモリ）の確定値**（5.5節）: 実装時にコンポーネントごとの実測負荷を踏まえて調整する。
5. **Bedrockのチャット・エンベディングモデルの具体的な選定**（ADR-0031で方針は確定、具体的なモデルIDは未確定）: 実装時にモデルアクセスの有効化状況・料金・性能を踏まえて確定する。

## 12. 実装着手前に確認をお願いしたい事項（再掲）

本書0節の内容（アクセス範囲、コンピュート基盤、`agent_invitro`実行形態、DB配置、認証方針、state管理、環境固有設定管理、MCP Inspector実行方式、`db_hiroba_qa_init`展開方式）は、いずれも発注者により確認・承認済みであり、実装着手可能な状態にある。

ただし、次の点は実装着手前に必ず対応すること。

- AWSアカウントID・リージョンの実値（11章 Open Issue 1）を発注者から受領すること。
- LLM接続先はAmazon Bedrockへ切り替えることが確定した（ADR-0031、11章 Open Issue 2解消）。対応するアプリケーションコードの変更はIMPL-202608101616として別途整理済みである。**Phase 3（コンテナイメージビルド）着手前に、IMPL-202608101616に基づくアプリケーションコードの実装が完了している必要がある。** 未完了のまま本書のPhase 3以降に着手すると、AWS環境で起動したコンテナがLM Studioへの到達を試みて失敗する。
