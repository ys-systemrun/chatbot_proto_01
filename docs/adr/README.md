# ADR一覧（Architecture Decision Records）

Knowledge MCP サーバ・Tag Selector MCP サーバ・QA/タグ管理UI（front_dev/web_backend拡張）・db_hiroba_qa_init（DBマイグレーション・シード分離）・agent_invitro（Conversation Agent実験）・MCPサーバー/クライアントのAWSデプロイに関する設計判断の記録。各ファイルは Michael Nygard 形式（コンテキスト／決定／代替案／結果）に準拠。

| No. | タイトル | ステータス |
|---|---|---|
| [0001](./0001-knowledge-mcp-repo-placement.md) | Knowledge MCP サーバの配置（モノレポ構成） | Accepted |
| [0002](./0002-knowledge-mcp-transport.md) | 実行形態・通信方式（独立コンテナ + HTTP/SSE） | Accepted |
| [0003](./0003-knowledge-mcp-vector-store.md) | ベクトルストア方針（既存pgvectorを継続利用） | Accepted |
| [0004](./0004-knowledge-mcp-mvp-scope.md) | MVPスコープ（QA JSON Adapterのみ初回実装） | Accepted |
| [0005](./0005-knowledge-mcp-tag-relational-model.md) | タグの関連テーブル化（将来のツリー構造対応を見据えて） | Accepted |
| [0006](./0006-knowledge-mcp-tag-management-tools.md) | タグマスタ管理機能をKnowledge MCPのツールとして提供する | Accepted |
| [0007](./0007-tag-selector-mcp-repo-placement-and-transport.md) | Tag Selector MCP サーバの配置・実行形態（Knowledge MCPと同一方針を踏襲） | Accepted |
| [0008](./0008-tag-selector-mcp-taxonomy-source-of-truth.md) | タグ知識ベースの正本（既存tagテーブルを正本とし、taxonomy.yaml方式は不採用） | Accepted |
| [0009](./0009-tag-selector-mcp-mvp-selection-algorithm.md) | MVPのタグ選択アルゴリズム（Embedding層・階層探索は見送り） | Accepted |
| [0010](./0010-tag-selector-mcp-response-format.md) | レスポンス形式（選択タグ一覧のみ、SearchPlan/階層展開は将来スコープ） | Accepted |
| [0011](./0011-tag-selector-mcp-cache-policy.md) | タグ知識ベースのキャッシュ方針（起動時ロード＋明示的リロード＋定期ポーリング） | Accepted |
| [0012](./0012-tag-selector-mcp-mvp-llm-provider.md) | MVP時点のLLM接続先をローカルLLM（LM Studio）とする | Accepted |
| [0013](./0013-admin-ui-writes-via-knowledge-mcp.md) | 管理UIからのQA・タグ書き込み経路をKnowledge MCP経由に統一する | Accepted |
| [0014](./0014-knowledge-mcp-qa-management-tools.md) | QAデータの登録・編集機能をKnowledge MCPのツールとして追加する | Accepted |
| [0015](./0015-front-dev-admin-routing.md) | front_dev管理画面のルーティング方式（管理画面サブツリー限定でreact-router-dom導入） | Accepted |
| [0016](./0016-db-hiroba-qa-init-service-separation.md) | db_hiroba_qa_init サービスの分離（マイグレーション・シード責務の集約） | Accepted |
| [0017](./0017-db-hiroba-qa-init-migration-tool-selection.md) | マイグレーションツールの選定（yoyo-migrations採用、embedding次元のパラメータ化） | Accepted |
| [0018](./0018-db-hiroba-qa-init-seed-idempotency-and-startup-order.md) | シード実行制御（存在チェックによる冪等性）・起動順序制御方式 | Accepted |
| [0019](./0019-agent-invitro-repo-placement-and-execution-form.md) | agent_invitro（Conversation Agent実験）の配置・実行形態（常駐HTTPサーバー化せずIPython対話シェル用コンテナとする） | Accepted |
| [0020](./0020-agent-invitro-llm-provider.md) | agent_invitro（実験）が使用するLLM接続先（ADR-0012と同一方針でローカルLLM/LM Studio） | Accepted |
| [0021](./0021-agent-invitro-mcp-client-implementation.md) | LangGraphからMCPサーバー群への接続実装方式（langchain-mcp-adaptersを採用） | Accepted |
| [0022](./0022-agent-invitro-graph-structure.md) | agent_invitro のグラフ構造（LLMが自律的にツールを選ぶReActエージェント方式を採用） | Accepted |
| [0023](./0023-mcp-aws-deployment-internal-access-scope.md) | MCPサーバー・クライアント群をAWSへデプロイする際のアクセス範囲・ネットワーク境界方針（AWS内部限定、外部公開・オンプレVPN接続なし） | Accepted |
| [0024](./0024-mcp-aws-compute-platform-ecs-fargate.md) | MCPサーバー・クライアント群のコンピュート基盤（ECS Fargate採用） | Accepted |
| [0025](./0025-agent-invitro-aws-execution-form.md) | agent_invitroのAWS上での実行形態（ECS Fargate常駐化・ECS Exec方式） | Accepted |
| [0026](./0026-mcp-aws-database-rds-migration.md) | 既存DB（pgvector）のAWS上での配置方針（Amazon RDS for PostgreSQLへ移行） | Accepted |
| [0027](./0027-terraform-state-s3-backend.md) | Terraform state管理方式（S3バックエンド採用） | Accepted |
| [0028](./0028-terraform-env-specific-config-tfvars.md) | AWSアカウント・リージョン等の環境固有設定の管理方式（Git管理外のterraform.tfvars） | Accepted |
| [0029](./0029-mcp-inspector-verification-ecs-exec.md) | MCP Inspectorによるプロトコル層検証の実行方式（ECS Execによる一時検証タスク） | Accepted |
| [0030](./0030-db-hiroba-qa-init-aws-deployment.md) | db_hiroba_qa_initのAWS展開方式（ECR + ECSによるマイグレーション・シード実行） | Accepted |
| [0031](./0031-aws-llm-provider-bedrock.md) | AWS環境におけるLLM接続先をAmazon Bedrockへ切り替える（チャット・エンベディング） | Accepted |
| [0032](./0032-agent-invitro-flatten-src-layout.md) | agent_invitroのディレクトリ構成の平坦化（`src/agent_invitro/`→`src/`） | Accepted |
| [0033](./0033-agent-invitro-settings-injection.md) | agent_invitroのllm.py・mcp_clients/client.pyをSettingsへ直接依存させず、main.pyから引数注入する構成へ変更 | Accepted |
| [0034](./0034-db-hiroba-qa-init-seed-data-bundled-as-sql.md) | db_hiroba_qa_initのシード元データ（CSV/JSON）をイメージに同梱する（AWSデプロイ対応） | Accepted |
| [0035](./0035-db-hiroba-qa-init-embedding-cache-reuse.md) | db_hiroba_qa_initにembeddingキャッシュ再利用オプションを追加する（destroy→再apply時のBedrock再計算回避） | Accepted |

関連する要件定義書:
- `docs/requirement/202608041002.md`（Knowledge MCP サーバ）
- `docs/requirement/202608051636.md`（Tag Selector MCP サーバ）
- `docs/requirement/202608060826.md`（QAデータ・タグ管理UI: front_dev / web_backend 拡張）
- `docs/requirement/202608061016.md`（db_hiroba_qa_init: DBマイグレーション・シード専用サービスの分離）
- `docs/requirement/202608061621.md`（agent_invitro: Conversation Agent（LangGraph MCPホスト）実験）
- `docs/requirement/202608100910.md`（MCPサーバー・クライアント AWS デプロイ）
