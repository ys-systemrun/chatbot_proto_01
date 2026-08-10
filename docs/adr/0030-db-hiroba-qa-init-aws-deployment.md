# ADR-0030: `db_hiroba_qa_init`のAWS展開方式（ECR + ECSによるマイグレーション・シード実行）

- ステータス: Accepted
- 日付: 2026-08-10
- 関連: `docs/requirement/202608100910_MCPサーバークライアントAWSデプロイ要件定義書.md`, ADR-0016, ADR-0017, ADR-0018, ADR-0024, ADR-0026

## コンテキスト

`knowledge_mcp`が利用するDBをAmazon RDS for PostgreSQL（pgvector拡張）へ移行する方針が確定した（ADR-0026）。このRDSに対して、既存の`db_hiroba_qa_init`（ADR-0016〜0018でマイグレーション・シード責務を集約したサービス、yoyo-migrations採用、存在チェックによる冪等性を持つ）と同等の処理をどう実行するかが、要件定義書 Open Issue #8として残っていた。

検討した選択肢は次の2案。

1. **`db_hiroba_qa_init`をAWSにも展開する**: 既存のDockerイメージをAmazon ECR（Elastic Container Registry）にpushし、ECS（Fargate）上でタスクとして実行し、RDSに対してマイグレーション・シードを行う。
2. **本検証（MVP）に限り、VPC内部から最小限のデータを手動投入する**: `db_hiroba_qa_init`自体はAWSに展開せず、一時的な検証用タスク（ADR-0029のMCP Inspector検証用タスクと同様の仕組み）から`psql`等で直接必要最小限のデータのみを投入する。

## 決定

**案1（`db_hiroba_qa_init`をECR + ECSでAWSにも展開する）を採用する。**（発注者確認済み）

`db_hiroba_qa_init`の既存Dockerイメージをそのまま利用し、Amazon ECRにpushする。ECS Fargate上で**常駐サービスではなく、一回限り実行して終了するタスク**（`aws ecs run-task`によるRun Task方式）として起動し、RDS（ADR-0026）に対してマイグレーション（yoyo-migrations）・シード（既存の冪等性チェック、ADR-0018）を実行する。他3コンポーネント（`knowledge_mcp`・`tag_selector_mcp`・`agent_invitro`、ADR-0024, 0025）が常駐ECS Fargateサービスであるのに対し、`db_hiroba_qa_init`は起動・実行・終了する一時的なタスクとして扱う点が異なる。

## 検討した代替案

- **案2（VPC内部からの手動データ投入）**: 追加のECR/ECSリソースを用意せずに済むが、既存の`db_hiroba_qa_init`が持つマイグレーション管理・冪等なシード処理（ADR-0016〜0018）を再利用できず、手動投入の内容とローカル環境の`db_hiroba_qa_init`が管理するスキーマ・データとの整合を維持する負担が生じる。ローカルとAWSで異なる手順・ツールを使うことになり、保守性の観点でも望ましくないため不採用とした。

## 結果・影響

- Terraformモジュール構成（要件定義書6.5節）に、`db_hiroba_qa_init`用のECRリポジトリおよびRun Task用のタスク定義を追加する必要がある。なお、ECRリポジトリ自体は`knowledge_mcp`・`tag_selector_mcp`・`agent_invitro`の3コンポーネントについても、ECS Fargateでイメージを実行するために元来必要な前提であり、本ADRを機に4コンポーネント共通の要件として明示する。
- RDS（ADR-0026）のセキュリティグループには、`knowledge_mcp`からの通信に加え、**`db_hiroba_qa_init`からRDSへの通信も許可する**必要がある（マイグレーション・シードはRDSへ直接接続して実行するため）。要件定義書6.7節のアクセス制御方針をこの点で更新する。
- ECSタスク実行ロールに、ECRからのイメージ取得権限（`ecr:GetAuthorizationToken`等、標準のタスク実行ロールポリシーに含まれる）を付与する。
- `db_hiroba_qa_init`はADR-0018の冪等性設計（存在チェックによる冪等なシード）を前提に、必要なタイミング（初回検証データ投入時、マイグレーション追加時等）で都度実行する運用とする。実行手順（`aws ecs run-task`の具体的な呼び出し方法、完了確認方法）は実装フェーズで確定する。
- `knowledge_mcp`サービスの起動・更新は、`db_hiroba_qa_init`タスクの実行完了後に行う必要がある（ADR-0018の起動順序制御という関心事に相当）。ただしECSには、docker-composeの`depends_on: condition: service_healthy`に相当するタスク間の自動順序制御機能がないため、この順序保証はデプロイ手順（Terraform適用やCI/CDのステップ順序）側で担保する運用ルールとして扱う。
