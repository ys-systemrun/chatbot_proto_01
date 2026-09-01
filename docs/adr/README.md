# ADR一覧（Architecture Decision Records）

Knowledge MCP サーバ・Tag Selector MCP サーバ・QA/タグ管理UI（front_dev/web_backend拡張）・db_hiroba_qa_init（DBマイグレーション・シード分離）・agent_invitro（Conversation Agent実験）・MCPサーバー/クライアントのAWSデプロイ・Terraform構成再編・AWS環境向け管理UIのブラウザアクセス・AWS環境向けChatbotUI・会話評価機能有効化・全データエクスポート機能・検索精度検証機能・DBマイグレーション/データインポート機能・会話タグ管理機能・タグ階層展開とタグ構成類似度スコアリング・検証機能の既存タグ入力・管理画面一覧ページの検索条件URL同期に関する設計判断の記録。各ファイルは Michael Nygard 形式（コンテキスト／決定／代替案／結果）に準拠。

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
| [0036](./0036-network-existing-vpc-reference.md) | ネットワーク基盤（VPC・サブネット）の外部管理化（既存VPC・サブネットをdata sourceで参照） | Accepted |
| [0037](./0037-terraform-state-database-separation.md) | Terraform state分割方針（DB実体を独立stateに分離し、destroy対象から除外） | Accepted |
| [0038](./0038-shared-terraform-config-env-consolidation.md) | 複数state層にまたがる共通設定値の集約方式（`.env`からのTF_VAR_*環境変数エクスポート） | Accepted |
| [0039](./0039-terraform-state-two-layer-consolidation.md) | Terraform state 3層構成から2層構成（database構成/app構成）への統合 | Accepted |
| [0040](./0040-deploy-orchestration-containerized-python.md) | デプロイオーケストレーションのコンテナ内Python化と設定の単一.env集約（PS5.1脱却） | Accepted |
| [0041](./0041-admin-ui-aws-network-exposure.md) | 管理UI（admin_uiサービス）のAWSネットワーク配置とブラウザアクセス経路（ADR-0023の限定的な見直し） | Accepted |
| [0042](./0042-admin-ui-static-asset-serving.md) | front_dev本番ビルド資産の配信方式（web_backendコンテナからの単一サービス配信） | Accepted |
| [0043](./0043-agent-invitro-http-service-ask-sl.md) | agent_invitroの常駐HTTPサービス化とチャット生成（/ask-sl）機能の実装移管（AWS環境限定） | Accepted |
| [0044](./0044-conversation-db-aws-placement.md) | 会話履歴・評価データ（conversationデータベース）のAWS上の配置とスキーマ管理方式 | Accepted |
| [0045](./0045-admin-ui-agent-invitro-integration-and-conversation-db-access.md) | admin_ui⇄agent_invitro間のチャット生成連携、およびconversationデータベースへの直接アクセス（ADR-0041の限定的な見直し） | Accepted |
| [0046](./0046-chatbot-db-export-readonly-access.md) | chatbotデータベースのエクスポート専用読み取り経路の新設（ADR-0013・ADR-0041の限定的な見直し） | Accepted |
| [0047](./0047-data-export-dump-generation-and-delivery.md) | 全データエクスポート機能のダンプ生成方式・配信方式（SQL/CSV、同期ストリーミングダウンロード） | Accepted |
| [0048](./0048-verification-data-placement-and-access-path.md) | 検証機能のデータ配置・アクセス経路（conversationデータベースに新設、web_backendが直接読み書き） | Accepted |
| [0049](./0049-verification-pipeline-scope-and-tag-selector-mcp-client.md) | 検証実行パイプラインの範囲（tag_selector_mcp→knowledge_mcpの2段検索のみ）とTag Selector MCPクライアントの新設 | Accepted |
| [0050](./0050-verification-question-management-and-run-history-retention.md) | 検証対象質問の管理方式（登録制・再実行可能）と実行履歴の保持方針（実行単位で履歴・評価を保持） | Accepted |
| [0051](./0051-conversation-db-migration-tool-adoption.md) | conversationデータベースのマイグレーション方式をyoyo-migrationsへ統一する（ADR-0044の限定的な見直し） | Accepted |
| [0052](./0052-chatbot-db-migration-role-separation.md) | chatbotデータベースのマイグレーション実行ロールの権限分離 | Accepted |
| [0053](./0053-qa-tag-bulk-import-via-knowledge-mcp.md) | QA・タグデータの一括インポート機能の実装方式（Knowledge MCP経由のバッチツール新設） | Accepted |
| [0054](./0054-verification-question-bulk-import.md) | 検証質問データの一括インポート機能の実装方式（verification_db直接書き込み） | Accepted |
| [0055](./0055-full-data-import-execution-path.md) | 全データインポート機能の実装方式とアクセス経路 | Accepted |
| [0056](./0056-conversation-tag-client-management-and-api-contract.md) | 会話タグの管理主体とAPI契約（クライアントエコー方式、DB非永続化） | Accepted |
| [0057](./0057-agent-invitro-tag-merged-search-and-continuation-logic.md) | agent_invitroにおける会話タグの検索反映方式と継続タグ判定ロジック | Accepted |
| [0058](./0058-knowledge-mcp-tag-ancestor-expansion.md) | search_knowledgeにおける祖先タグの動的展開方式（クエリ時再帰CTEによる閉包計算、qa_tagは変更しない） | Accepted |
| [0059](./0059-knowledge-mcp-tag-similarity-scoring.md) | タグ構成類似度と埋め込み類似度を統合したスコアリング方式（AND完全一致を廃止しJaccard係数ベースのランキングへ） | Accepted |
| [0060](./0060-verification-existing-tags-parameter-and-new-tag-recording.md) | 検証機能への既存タグ入力パラメータ追加と新規タグのみの記録方針 | Accepted |
| [0061](./0061-tag-bulk-import-via-knowledge-mcp.md) | タグ単体の一括インポート機能の実装方式（Knowledge MCP経由の新規バッチツール、タグ名によるupsert） | Accepted |
| [0062](./0062-agent-invitro-tag-search-single-call-simplification.md) | agent_invitroの情報源検索を単一search_knowledge呼び出しに単純化（ADR-0057の限定的な見直し） | Accepted |
| [0063](./0063-agent-invitro-mcp-adapter-result-parsing-fix.md) | agent_invitroのMCPツール戻り値パース頑健化（会話タグが常に空になる不具合の修正、ADR-0062の診断見直し） | Accepted |
| [0064](./0064-question-altered-management-via-knowledge-mcp.md) | 言い換え質問文（question_altered）管理機能の実装方式（Knowledge MCP経由、一覧・作成・編集・削除・CSVインポート/エクスポート、主質問文行を対象外とする設計） | Accepted |
| [0065](./0065-tag-export-via-knowledge-mcp.md) | タグ階層データのCSVエクスポート機能の実装方式（Knowledge MCP新規ツールによるフラット化、既存インポート列構成との統一） | Accepted |
| [0067](./0067-qa-record-deletion-cascade.md) | QAレコード削除機能の実装方式（カスケード削除・一覧編集両ページからの単一削除） | Accepted |
| [0068](./0068-admin-list-pages-search-state-url-sync.md) | 管理画面一覧ページ（QA一覧・言い換え質問文一覧）の検索条件・ページ位置のURL同期方式 | Accepted |

関連する要件定義書:
- `docs/requirement/202608041002.md`（Knowledge MCP サーバ）
- `docs/requirement/202608051636.md`（Tag Selector MCP サーバ）
- `docs/requirement/202608060826.md`（QAデータ・タグ管理UI: front_dev / web_backend 拡張）
- `docs/requirement/202608061016.md`（db_hiroba_qa_init: DBマイグレーション・シード専用サービスの分離）
- `docs/requirement/202608061621.md`（agent_invitro: Conversation Agent（LangGraph MCPホスト）実験）
- `docs/requirement/202608100910.md`（MCPサーバー・クライアント AWS デプロイ）
- `docs/requirement/202608180957.md`（Terraform構成再編: 3層→2層統合）
- `docs/requirement/202608211014.md`（AWS環境向けQA・タグ管理UI: ブラウザアクセスの実現）
- `docs/requirement/202608240949_AWS環境向けChatbotUI・会話評価機能有効化要件定義書.md`（AWS環境向けChatbotUI・会話評価機能有効化: チャット生成のagent_invitroへの移管と会話評価データベースの配置）
- `docs/requirement/202608241530_全データエクスポート機能要件定義書.md`（全データエクスポート機能: ブラウザボタンからのSQL/CSVエクスポート）
- `docs/requirement/202608260909_質問タグ情報源検索精度検証機能要件定義書.md`（質問→タグ→情報源 検索精度検証機能: 登録した質問に対するタグ選択・情報源検索の実行結果一覧化とDB保存）
- `docs/requirement/202608271040_agent_invitroタグマージ検索方式単純化要件定義書.md`（agent_invitroタグマージ検索方式単純化: ADR-0057のタグ別複数回呼び出しワークアラウンドを、検証機能（ADR-0060）と同じ単一search_knowledge呼び出し方式に統一）
- `docs/requirement/202608271500_agent_invitroタグ選択結果取得不具合修正要件定義書.md`（agent_invitroタグ選択結果取得不具合修正: langchain-mcp-adaptersの戻り値パース欠陥で会話タグが常に空になる不具合の是正。select_tags/search_knowledge戻り値パースの頑健化と診断ログ追加）
- `docs/requirement/202608261002_DBマイグレーション・データインポート機能要件定義書.md`（DBマイグレーション・データインポート機能: conversationデータベースのマイグレーション方式統一、QA・検証質問の一括インポート、全データインポート機能の整理）
- `docs/requirement/202608261330_会話タグ管理機能要件定義書.md`（会話タグ管理機能: クライアント側でのタグ管理、agent_invitroでのselect_tagsとのマージ・継続タグ判定）
- `docs/requirement/202608261450_タグ階層展開・タグ構成類似度スコアリング機能要件定義書.md`（knowledge_mcpのsearch_knowledge: 祖先タグの動的展開とタグ構成類似度・埋め込み類似度を統合したスコアリングへの変更）
- `docs/requirement/202608261510_検証機能既存タグ入力・新規タグ記録機能要件定義書.md`（検証機能拡張: 検証質問への既存タグ入力、select_tags結果との差分による新規タグのみの記録）
- `docs/requirement/202608261600_タグデータ一括インポート機能要件定義書.md`（タグデータ一括インポート機能: タグ単体の一括登録・更新、タグ名によるupsert、親タグ名による階層指定）
- `docs/requirement/202608271750_言い換え質問文（question_altered）管理機能要件定義書.md`（言い換え質問文（question_altered）管理機能: 一覧・CSV一括インポート・新規作成・編集・削除ページ、および言い換え行単体のCSVエクスポート機能の追加）
- `docs/requirement/202608281421_タグデータCSVエクスポート機能要件定義書.md`（タグデータCSVエクスポート機能: タグ階層ページに、タグ一括インポート（ADR-0061）とそのまま再インポートできる列構成でのCSVエクスポート機能を追加）
- `docs/requirement/202608311540_QAレコード削除機能要件定義書.md`（QAレコード削除機能: QA一覧ページ・QA編集ページからのQAレコード削除、カスケード削除・クロスデータベース整合性の告知）
- `docs/requirement/202608311600_QA一覧・言い換え質問文一覧ページ検索条件URL保持機能要件定義書.md`（QA一覧・言い換え質問文一覧ページの検索条件・ページ位置のURL保持機能: URLクエリからの検索条件注入、編集後の一覧復帰時の検索条件・ページ位置保持）
