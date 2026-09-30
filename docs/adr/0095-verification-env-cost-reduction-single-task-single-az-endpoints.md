# ADR-0095: 検証環境のコスト削減 — 常駐4サービスを1タスクへ集約し、VPCエンドポイントを単一AZに限定する

- ステータス: Accepted
- 日付: 2026-09-30
- 関連: ADR-0024（ECS Fargate採用）、ADR-0025（agent_invitroのAWS実行形態）、ADR-0026（RDS移行）、ADR-0036（既存VPC参照）、ADR-0039（state 2層構成）、ADR-0040（コンテナ内Pythonオーケストレータ）、ADR-0041（admin_uiのネットワーク配置）、ADR-0043（agent_invitroの常駐HTTPサービス化）、ADR-0045（資格情報スコープ）、ADR-0052（DBロール分離）、ADR-0066（全データインポート）

## コンテキスト

現在の Terraform 構成（`terraform/main/app`）は、常駐サービスを **4つの独立した ECS サービス（＝4タスク）** として起動している。

| サービス | ポート | タスクサイズ | 接続方式 |
|---|---|---|---|
| `tag_selector_mcp` | 8200 | 0.5 vCPU / 1 GB | Service Connect（サーバ） |
| `knowledge_mcp` | 8100 | 0.5 vCPU / 1 GB | Service Connect（サーバ） |
| `agent_invitro` | 8300 | 0.5 vCPU / 1 GB | Service Connect（サーバ／クライアント） |
| `admin_ui` | 8000 | 0.5 vCPU / 1 GB | ALB 配下 + Service Connect（クライアント） |

また database 構成（`modules/network`）は、NAT を持たないプライベートサブネットから ECR・CloudWatch Logs・Secrets Manager・ECS Exec・Bedrock へ到達するため、**Interface 型 VPC エンドポイント7種**（`ecr.api` / `ecr.dkr` / `logs` / `secretsmanager` / `ssm` / `ssmmessages` / `bedrock-runtime`）を `private_subnet_ids` の**全サブネット（2 AZ）** に作成している。

このデプロイ先はあくまで**検証環境**であり、可用性よりも月額費用の低さを優先したい。us-east-1 の単価で常時起動した場合の概算は次のとおり。

| 項目 | 現状の月額概算 | 算出根拠 |
|---|---|---|
| Interface VPC エンドポイント | 約 $102 | 7種 × 2 AZ × $0.01/時 × 730時間（データ処理料は別） |
| Fargate 常駐4タスク | 約 $72 | 4 × (0.5 × $0.04048 + 1 × $0.004445)/時 × 730時間 |
| ALB | 約 $16〜22 | 固定料金 + LCU |
| RDS db.t4g.micro（Single-AZ） | 約 $12〜15 | インスタンス + ストレージ |

費用の大半は **VPC エンドポイントと Fargate タスクの数に比例する固定費**である。どちらも検証環境では冗長化の恩恵が小さい。

- Fargate は**タスク単位で課金**される。1つのタスク定義に複数コンテナを並べれば、イメージを統合しなくてもタスク数を減らせる。同一タスク内のコンテナはネットワーク名前空間を共有するため、`localhost:<port>` で相互に通信できる。
- Interface エンドポイントは **AZ（ENI）ごとに課金**される。エンドポイントの ENI が1つの AZ にしか無くても、VPC 内の他 AZ からの通信はプライベート DNS 経由で到達できる（AZ 間データ転送料が小さく発生する）。

一方、`private_subnet_ids` は RDS の DB サブネットグループにも使われている（`main/database/main.tf` の `module.database.subnet_ids`）。DB サブネットグループは **2 AZ 以上のサブネットを必須**とするため、この変数を単純に1サブネットへ減らすことはできない。

## 決定

**常駐4サービスを1つの ECS サービス（1タスク・4コンテナ）へ集約する。あわせて Interface VPC エンドポイントと ECS タスクの配置を単一 AZ の1サブネットに限定する。各サービスのイメージ・ECR リポジトリ・Dockerfile は分けたまま維持する。**

### 決定1: 1タスク定義に4コンテナを並べる（イメージは統合しない）

- `aws_ecs_task_definition` を1つ（family 例: `chatbot_invitro_app`）にし、`container_definitions` に `tag_selector_mcp` / `knowledge_mcp` / `agent_invitro` / `admin_ui` の4コンテナを定義する。
- 各コンテナのイメージは従来どおり個別の ECR リポジトリ（`knowledge-mcp` / `tag-selector-mcp` / `agent-invitro` / `admin-ui`）から取得する。**supervisord 等で1イメージへ統合する方式は採らない**（代替案参照）。
- タスクサイズは初期値 **1 vCPU / 2 GB** とする（現状4タスク合計 2 vCPU / 4 GB の半分）。CloudWatch の使用率を見て調整できるよう、変数（`app_task_cpu` / `app_task_memory`）で上書き可能にする。
- 4コンテナとも `essential = true` とする。いずれかが停止した場合はタスク全体を再起動させ、中途半端な状態で動き続けることを避ける。
- ポートは従来どおり 8000 / 8100 / 8200 / 8300 で、重複しない。

### 決定2: サービス間通信は `localhost` とし、Service Connect を廃止する

- 環境変数の接続先を次のように変更する。

  | 環境変数 | 変更前 | 変更後 |
  |---|---|---|
  | `KNOWLEDGE_MCP_URL` | `http://knowledge_mcp:8100/mcp` | `http://localhost:8100/mcp` |
  | `TAG_SELECTOR_MCP_URL` | `http://tag_selector_mcp:8200/mcp` | `http://localhost:8200/mcp` |
  | `AGENT_INVITRO_BASE_URL` | `http://agent_invitro:8300` | `http://localhost:8300` |

- Service Connect（`service_connect_configuration`）と、名前空間を作る `modules/service-discovery` の呼び出しを削除する。各タスクに付いていた Envoy サイドカーのリソース消費も無くなる。
- 起動順序はコンテナの `dependsOn` で担保する。`agent_invitro` と `admin_ui` は、`knowledge_mcp` と `tag_selector_mcp` の `HEALTHY`（既存の curl ヘルスチェック）を待ってから起動する。これにより、従来 `deploy` が行っていた「サーバ安定後に agent_invitro を強制再デプロイする」整合処理（`commands.py` の `_reconcile_agent_after_servers`）は不要になり、削除する。

### 決定3: シード完了ゲートはタスク全体の desired_count で扱う

- 従来は `knowledge_mcp_desired_count` で knowledge_mcp だけを seed 完了まで停止していた（Phase 4→5 ゲート）。集約後は個別に止められないため、**集約サービス全体の desired_count**（変数名 `app_desired_count`）をゲートに使う。
- `apply-all` の流れは「app apply（`app_desired_count=0`）→ seed run-task → app apply（`app_desired_count=1`）」となる。seed 完了までは tag_selector_mcp と admin_ui も起動しないが、検証環境では許容する。
- `deploy` の CLI 引数・`test_gate.py` など、`knowledge_mcp_desired_count` を参照している箇所を改名に合わせて更新する。

### 決定4: 全データインポートの停止対象は集約サービス1つにする

- ADR-0066 の全データインポートは、対象 DB に接続するサービス（`admin_ui` / `knowledge_mcp` / `tag_selector_mcp`）を個別に停止していた。集約後は **集約サービスを desired_count=0 にして全体を止める**。
- 以前は停止対象外だった agent_invitro も一緒に止まるが、インポート中はチャット機能も使えないため実害はない。
- `commands.py` の `_IMPORT_SERVICES_BY_DB` は、どの DB を対象にしても集約サービス1つを返すように単純化する。

### 決定5: セキュリティグループ・IAM は集約サービス単位に統合する（資格情報の注入はコンテナ単位を維持）

- **セキュリティグループ**: タスクの ENI は1つになるため、`sg_tag_selector_mcp` / `sg_knowledge_mcp` / `sg_agent_invitro` / `sg_admin_ui_task` を1つの `sg_app_task` に統合する。インバウンドは「ALB → 8000」と「verification_task → 8100 / 8200」だけを残し、サービス間のルールは削除する（同一タスク内の通信は SG を通らないため）。RDS へのインバウンドは `sg_app_task` からの 5432 に一本化する。
- **Secrets の注入**: コンテナ定義ごとに `secrets` を指定できるため、**どのコンテナにどの接続文字列を渡すかは従来どおり**とする。
  - `knowledge_mcp` / `tag_selector_mcp`: `chatbot_app` ロールの `DATABASE_URL`
  - `admin_ui`: `CONVERSATION_DB_URL`（`conversation_app` ロール）と `CHATBOT_EXPORT_DB_URL`
  - `agent_invitro`: DB 資格情報なし

  これにより ADR-0045 の「admin_ui にマスター権限の DATABASE_URL を渡さない」は維持される。
- **IAM ロール**: 実行ロールとタスクロールは1つずつになる。実行ロールには全コンテナが使う Secrets の和集合を許可する。タスクロールには Bedrock 呼び出し権限と ECS Exec 用の ssmmessages 権限を付与する。**admin_ui コンテナも Bedrock を呼べる権限を持つことになる**点は、検証環境の受容リスクとする（結果・影響を参照）。
- ECS Exec（ADR-0025）は `--container <名前>` を指定すれば、従来どおりコンテナ単位で利用できる。

### 決定6: Interface VPC エンドポイントと ECS タスクを単一 AZ の1サブネットに置く

- database 構成に新変数 `workload_subnet_id`（単一のプライベートサブネット ID）を追加する。未指定の場合は `private_subnet_ids[0]` を既定値とする。
- 次のリソースは `workload_subnet_id` だけを使うよう変更する。
  - Interface VPC エンドポイント7種の `subnet_ids`
  - 集約 ECS サービスの `network_configuration.subnets`
  - run-task 群（seed / migrate / query / import-data / MCP Inspector）の `subnets`。`deploy` は新しい出力 `workload_subnet_ids` を参照する。
- `private_subnet_ids`（2 AZ）は **RDS の DB サブネットグループ専用**として残す。RDS は Single-AZ（`multi_az=false`）のまま変更しない。
- S3 ゲートウェイ型エンドポイントは無料でルートテーブル単位のため、変更しない。
- エンドポイント7種は削らずに維持する。`ssm` / `ssmmessages` は ECS Exec（ADR-0025・ADR-0029）に、それ以外はイメージ取得・ログ・Secrets 注入・Bedrock 呼び出しに必須であるため。

### 決定7: ALB は2つの AZ のまま維持する

ALB は仕様上2つ以上の AZ のパブリックサブネットを要求し、AZ 数で料金も変わらない。そのため ADR-0041 の構成（`public_subnet_ids`）をそのまま使う。ターゲット（集約タスク）が1つの AZ にしか無くても、ALB からは AZ をまたいで転送される。

## 検討した代替案

- **supervisord 等で4サービスを1イメージに統合する**: タスク数削減の効果は決定1と同じ。しかし Dockerfile・依存関係（Python パッケージの版競合）・ログの分離をやり直す必要があり、ローカルの docker compose 構成とも乖離する。ECS のコンテナ単位のヘルスチェック・`dependsOn`・コンテナ別ログ・ECS Exec の `--container` 指定といった利点も失う。費用効果が同じで改修量が大きいため不採用とした。
- **Fargate Spot を使う**: Fargate 料金が最大7割程度下がる。しかし中断時は2分前通知で停止し、検証中にタスクが落ちることがある。本 ADR の集約と組み合わせること自体は可能なので、中断が許容できるかを運用で確認したうえで、後続の判断に回す。
- **EC2（t4g.small 等）1台に docker compose で載せる**: 固定費は最も小さくなる。しかし ECS Fargate 前提の Terraform・`deploy` オーケストレータ・run-task 方式の seed / migrate / import（ADR-0030・ADR-0066）をすべて作り直すことになる。変更範囲が検証環境のコスト削減という目的に見合わないため不採用とした。
- **VPC エンドポイントをやめて NAT ゲートウェイを使う**: NAT ゲートウェイは1台で約 $33/月＋データ処理料で、エンドポイント7種の単一 AZ 版（約 $51/月）より安い。しかし、ADR-0023 のプライベート閉域という方針と、既存 VPC の経路を基盤チームが管理する前提（ADR-0036）に反する。既存 VPC 側に NAT が既に用意されている場合は、`create_vpc_endpoints=false` で本構成のエンドポイントを作らない選択肢が既にあるので、本 ADR では扱わない。
- **`private_subnet_ids` 自体を1サブネットに減らす**: 変数追加が不要で最も単純。しかし RDS の DB サブネットグループが 2 AZ 以上を必須とするため apply が失敗する。不採用とした。
- **サービスは分けたまま、各タスクを 0.25 vCPU / 0.5 GB に縮小する**: 構成の変更は最小で済む。しかし Python + Bedrock クライアント + Service Connect の Envoy を 0.5 GB に収めるのは余裕が無い。また、4タスク分の最小単価が積み上がるため、削減幅も集約より小さい。不採用とした。
- **使わない時間帯に desired_count=0 にするスケジュール停止**: Fargate 料金をさらに削れ、本 ADR とは両立する。停止中もエンドポイント・ALB・RDS の固定費は残る。スケジュール（EventBridge Scheduler 等）の設計は別 ADR とする。

## 結果・影響

### 費用（us-east-1、常時起動の概算）

| 項目 | 変更前 | 変更後 |
|---|---|---|
| Interface VPC エンドポイント | 約 $102 | 約 $51 |
| Fargate | 約 $72 | 約 $36（1 vCPU / 2 GB × 1タスク） |
| ALB | 約 $16〜22 | 変化なし |
| RDS | 約 $12〜15 | 変化なし |
| **合計** | **約 $200** | **約 $115〜125** |

Bedrock の呼び出し料金は使用量に比例し、本 ADR の影響を受けない。

### 受け入れるトレードオフ

- **単一 AZ 障害で環境全体が止まる**: エンドポイントとタスクが1つの AZ に集まるため。検証環境として許容する。
- **1コンテナの異常や1イメージの更新でも4サービスが同時に再起動する**: 特定のサービスだけを再デプロイすることはできなくなる。
- **IAM 権限の分離が弱くなる**: タスクロールが1つになり、admin_ui コンテナからも Bedrock を呼べる。DB 資格情報の注入はコンテナ単位のままなので、ADR-0045・ADR-0052 の資格情報スコープは維持される。**本番環境を構築する際は、本 ADR を適用せず従来のサービス分割構成に戻す**ことを前提とする。
- **seed 完了前は admin_ui・tag_selector_mcp も起動しない**（決定3）。
- **サービス単位の CloudWatch メトリクスが無くなる**: CPU・メモリはタスク単位でしか見えない（Container Insights を有効にすればコンテナ単位で見られる）。ロググループは従来どおりコンテナ単位で分けられる。

### 改修範囲

- `terraform/modules/ecs-app-task`: 集約専用モジュールを新設する（複数コンテナ定義・`dependsOn`・コンテナ単位のロググループ・1組の IAM ロール）。サービス単位の `modules/ecs-service` と Service Connect 名前空間の `modules/service-discovery` は削除する。
- `terraform/main/app/main.tf`: 4つのモジュール呼び出しを1つに置き換え、`service_discovery` を削除する。`knowledge_mcp_desired_count` を `app_desired_count` に改名する。
- `terraform/modules/network`: SG の統合（決定5）と、エンドポイントの `subnet_ids` を `workload_subnet_id` に変更する（決定6）。
- `terraform/main/database`: 変数 `workload_subnet_id` と出力 `workload_subnet_ids` を追加し、SG 出力を整理する。
- `terraform/deploy/src/commands.py`: ゲート変数の改名（CLI は `--app-desired-count`、旧名 `--knowledge-mcp-desired-count` も互換で受け付ける）、`_reconcile_agent_after_servers` を集約サービスの安定待機 `_wait_app_stable` に置き換え（失敗時は異常終了したコンテナのログを表示）、インポート時の停止対象を集約サービスに変更、run-task のサブネットを `workload_subnet_ids` に変更する。`tests/` も追随させる。
- `terraform/README.md` / `terraform/.env.example`: 構成図・手順・新変数（`TF_VAR_workload_subnet_id` / `TF_VAR_app_task_cpu` / `TF_VAR_app_task_memory`）を追記する。
- アプリケーションのコード・Dockerfile は変更しない（接続先は環境変数だけで切り替わる）。

### 移行時の注意

- ECS サービス名・タスク定義 family・SG が作り直しになる。**app 構成は destroy-app → apply-app で入れ替える**（RDS は database 構成側なので影響しない）。
- database 構成の SG 統合では、RDS の SG ルールも付け替わる。そのため app 構成を先に destroy して旧 SG の参照を外してから、database 構成を apply する。
- Interface エンドポイントの `subnet_ids` の変更はその場で更新され、作り直しにはならない。
