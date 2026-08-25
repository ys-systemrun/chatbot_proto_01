# ADR-0044: 会話履歴・評価データ（conversationデータベース）のAWS上の配置とスキーマ管理方式

- ステータス: Accepted
- 日付: 2026-08-24
- 関連: `docs/requirement/202608240949_AWS環境向けChatbotUI・会話評価機能有効化要件定義書.md`, ADR-0016, ADR-0017, ADR-0018, ADR-0026, ADR-0030, ADR-0037, ADR-0043, ADR-0045
- 参考（2026-08-21時点の同種の検討）: `docs/adr/_to_delete/0044-conversation-db-aws-placement.md`（データ配置自体の結論は同一だが、当時は`conversation`データベースへのアクセス元を`agent_invitro`とする前提だった点が本ADRと異なる。本ADRではADR-0045のとおり`admin_ui`が直接アクセスする）

## コンテキスト

ローカル`docker-compose`環境では、会話履歴・メッセージ評価（good/bad）を保存する`conversation_db`（PostgreSQL 16、`postgres:16`公式イメージ）が、QAデータ用の`db_hiroba_qa`（pgvector, `chatbot`データベース）とは別の独立したコンテナ・データベースとして稼働している。スキーマ（`conversation`テーブル・`message`テーブル、いずれも`CREATE TABLE IF NOT EXISTS`）は`db_conversation/init.sql`として用意され、PostgreSQL公式イメージの`docker-entrypoint-initdb.d`機能により、コンテナの初回起動時に自動適用される。

AWS上には、QAデータ用のAmazon RDS for PostgreSQLインスタンス（`chatbot-invitro-rds`、ADR-0026、`chatbot`データベースを保持）が既に構築済みである。しかし`conversation_db`に相当するAWSリソースは存在しない。ChatbotUI・会話評価機能をAWS上で有効化するには、会話履歴・評価データの保存先をAWS上に用意する必要がある。

`docker-entrypoint-initdb.d`のような「コンテナ初回起動時にSQLを自動適用する」仕組みは、Amazon RDSでは利用できない（RDSは新規データベースインスタンスの作成時に指定した単一の初期データベース名（`db_name`）のみを持ち、その後の追加データベース作成・テーブル作成は、SQLクライアントからの明示的な実行が必要になる）。

発注者から、`conversation`データベースの配置について「既存RDSに相乗り（推奨）」との回答を得ている。

## 決定

**会話履歴・評価データは、新規RDSインスタンスを立てず、既存の`chatbot-invitro-rds`インスタンス上に`conversation`という別データベースとして追加する。** スキーマ（`conversation`/`message`テーブル）の作成は、既存の`db_hiroba_qa_init`ワンショットサービス（ADR-0016〜0018）の責務を拡張し、同サービスに統合する。

- **データベースの追加**: `db_hiroba_qa_init`の起動シーケンスに、マスター権限で接続した上で`conversation`データベースの存在を確認し、無ければ`CREATE DATABASE conversation`を実行するステップを追加する。既存の`DATABASE_URL`シークレット（`chatbot`データベースを指す、マスターユーザー資格情報を含む）を使って`chatbot`データベース（または`postgres`デフォルトデータベース）に接続し、`CREATE DATABASE`を実行する。
- **接続文字列**: `terraform/modules/database`モジュールに、`conversation_db_name`変数（既定値`"conversation"`）と、`db_url_secret_arn`と同様の形式で組み立てた第2のSecrets Managerシークレット（`conversation_db_url_secret_arn`、ホスト・ポート・認証情報は`chatbot`用と同一、データベース名のみ異なる）を追加する。
- **環境変数名**: 既存のローカル`docker-compose.yml`および`web_backend/main/main_stateless.py`が使用している名称`CONVERSATION_DB_URL`に統一する（2026-08-21時点の廃案では`CONVERSATION_DATABASE_URL`という別名を用いていたが、既存コードとの一致を優先し、本ADRでは採用しない）。
- **テーブルスキーマの適用**: `conversation`/`message`テーブルは、`db_conversation/init.sql`と同内容の冪等なDDL（`CREATE TABLE IF NOT EXISTS`）を、`db_hiroba_qa_init`が新設した`conversation`データベースに対して直接実行する。既存の`chatbot`データベース用マイグレーション（yoyo-migrations、ADR-0017）とは別系統とし、yoyoによる履歴管理は導入しない（後述「検討した代替案」参照）。
- **冪等性**: `CREATE DATABASE`の存在チェック、テーブルDDLの`IF NOT EXISTS`により、既存の`db_hiroba_qa_init`と同様に何度再実行しても安全である（ADR-0018の冪等性方針を踏襲）。
- **実行順序**: 既存のデプロイオーケストレーション（`bootstrap` → `apply-database` → `seed`（`db_hiroba_qa_init`実行） → `apply-app`）に変更を加える必要はない。`conversation`データベースの作成・スキーマ適用は既存の`seed`ステップに統合されるため、`admin_ui`・`agent_invitro`（`apply-app`で起動）が起動する時点では`conversation`データベースの準備が完了している。
- **アクセス元**: `admin_ui`（`web_backend`）が`conversation`データベースへ直接読み書きする。ローカル`docker-compose`環境における現行実装（`ConversationDB`クラス、`web_backend/src/conversation_db/db.py`による直接psycopg2アクセス）と同一の責務分担をAWS上でも維持する（ADR-0045）。`agent_invitro`は`conversation`データベースへアクセスしない（ADR-0043）。

## 検討した代替案

- **新規RDSインスタンスとして分離する**: QAデータとライフサイクル（バックアップ・削除・スケール）を独立管理できる利点はあるが、追加のRDSインスタンス費用（`db.t4g.micro`でも時間課金）が発生する。2026-08-21時点で発注者から「MVPでは無期限保存でよく、厳密な運用要件はない」との回答を得ており、コストに対して過大と判断し見送った（本書要件定義書のOpen Issueとして改めて確認することを推奨する）。将来、会話データの保持期間・削除ポリシー・アクセス権限をQAデータと明確に分離する必要が生じた場合に再検討する。
- **HashiCorp/CyrilGDNの`postgresql`プロバイダ等を使ってTerraformで宣言的にデータベース・テーブルを管理する**: IaCとしての一貫性は高いが、既存構成（ADR-0016〜0018）が確立した「スキーマ作成・シードは`db_hiroba_qa_init`という専用ワンショットサービスに集約する」という設計方針と一致しないため不採用とした。
- **`conversation`テーブルにもyoyo-migrationsを導入する**: `chatbot`データベースと同じツールに統一できる利点があるが、現時点でのスキーマは2テーブル・1バージョンのみであり、ADR-0017がyoyo採用を決定した際の背景（複数マイグレーション・embedding次元パラメータ化への対応）が当てはまらない。過剰なツール導入と判断し、素の冪等DDL適用とした。
- **チャット機能を提供するサービス（`admin_ui`または`agent_invitro`）の起動時にアプリケーション側でテーブル作成を行う**: `ConversationDB`クラス自体はテーブル作成ロジックを持たず、既存スキーマの存在を前提にしている。起動時作成に変更するとアプリケーションコードの責務が増え、複数タスクが同時に`CREATE TABLE`を実行した場合の競合（`desired_count=1`のため通常は問題にならないが将来のスケールアウト時にリスクとなる）を避けるため、既存の`db_hiroba_qa_init`（ワンショット・単一実行が保証されている）に統合する方式を優先した。

## 結果・影響

- `terraform/modules/database`に`conversation_db_name`変数と`conversation_db_url_secret_arn`出力が追加される。`terraform/main/database/main.tf`・`terraform/main/app/main.tf`にこの出力を`admin_ui`サービスの`secrets`（`CONVERSATION_DB_URL`）として伝播する変更が必要になる（ADR-0045）。
- `db_hiroba_qa_init`（`db_hiroba_qa_init/src/main.py`、`migrations/`）にアプリケーションコードの変更が発生する（実装指示書で詳細を指示する）。
- `terraform/modules/network`に、`admin_ui_task → rds`（5432番）の到達性ルールが新規追加される（ADR-0045、ADR-0041の限定的な見直し）。`agent_invitro → rds`のルールは追加しない（ADR-0043のとおり不要）。
- 会話データの保持期間・削除方針は本ADRの範囲外とし、要件定義書のOpen Issueとして引き継ぐ（2026-08-21時点でMVPは無期限保存で問題ないとの回答があるが、本書で改めて確認する）。将来、個人情報・機密情報を含む会話内容の取り扱いについて社内規程・法令上の保持期間要件が明確になった場合、本ADRを見直し、自動削除・アーカイブの仕組みを別途検討する。
- ローカル`docker-compose`環境（`conversation_db`コンテナ、`db_conversation/init.sql`）には変更を加えない。
