# terraform/modules/ecs-app-task — 集約 ECS サービス（1タスク・4コンテナ）

常駐4サービス（tag_selector_mcp / knowledge_mcp / agent_invitro / admin_ui）を1タスク・複数コンテナで動かす ECS サービスとタスク定義のモジュール（ADR-0095。旧 ecs-service モジュールを置き換え）。
コンテナ間通信は同一タスク内の `localhost:<port>` で行い、Service Connect は使わない。`desired_count` がシード完了ゲート（`app_desired_count`）になる。
`terraform/main/app` から `module "app"` として呼ばれる。

## 構成

| 名前 | 説明 |
|---|---|
| [`variables.tf`](variables.tf) | 入力変数（名前・クラスタ・リージョン・タスク CPU/メモリ・コンテナ定義リスト・SG/サブネット・`desired_count`・ECS Exec・Bedrock 権限・ALB ターゲットグループ等） |
| [`main.tf`](main.tf) | コンテナごとのロググループ `/ecs/<コンテナ名>`、タスク定義（コンテナ定義の組み立て）、ECS サービス（パブリック IP 付き配置・ALB への登録）、出力 `task_definition_arn` / `service_name` / `task_role_arn` |
| [`iam.tf`](iam.tf) | タスク1つに対する実行ロール（イメージ pull・ログ・secrets 注入）とタスクロール（ECS Exec・Bedrock 呼び出し） |
