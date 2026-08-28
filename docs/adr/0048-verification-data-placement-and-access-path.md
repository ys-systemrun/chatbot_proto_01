# ADR-0048: 検証機能のデータ配置・アクセス経路

- ステータス: Accepted
- 日付: 2026-08-26
- 関連: `docs/requirement/202608260909_質問タグ情報源検索精度検証機能要件定義書.md`, ADR-0013, ADR-0044, ADR-0045

## コンテキスト

新規の検証機能（質問→タグ選択→情報源検索の実行結果を保存・一覧表示する機能、要件定義書1章）は、検証質問（マスタ）・検証実行（`select_tags`/`search_knowledge`結果のスナップショットを含む履歴）・評価（人による目視評価）をDBへ永続化する必要がある（発注者回答、要件定義書2章 回答2・4）。

保存先として、既存のDB構成には次の2つのPostgreSQLデータベースがある。

1. `chatbot`データベース（pgvector, `db_hiroba_qa`/AWSでは`chatbot-invitro-rds`）: QA・タグのマスタデータ（`qa_original`/`question_altered`/`tag`/`tag_alias`/`qa_tag`/`category`）を保持する。ADR-0013により、`web_backend`はこのデータベースへ直接書き込まず、必ずKnowledge MCPのMCPツール経由で読み書きする方針が確立している。
2. `conversation`データベース（`db_conversation`/AWSでは同一RDSインスタンス上の別データベース）: 会話履行・評価データ（`conversation`/`message`テーブル）を保持する。ADR-0044/0045により、`web_backend`（`admin_ui`）はこのデータベースへ直接（`psycopg2`による生SQL）読み書きする方針が確立している。ADR-0045は、この直接アクセスの許容範囲を「Knowledge MCPの管理対象（QA・タグ）ではない、会話履行・評価データ」に限定している。

検証機能が保存するデータ（検証質問・タグ選択結果・検索結果・評価）は、QA・タグのマスタデータそのものではなく、既存の会話評価データ（`message.evaluation`）と同様に「担当者による実行・評価の記録」という性質を持つ運用ログ的データである。

## 決定

**検証機能のデータ（検証質問・検証実行・選択タグ・情報源・評価）は、新規に4テーブル（`verification_question`/`verification_run`/`verification_run_tag`/`verification_run_source`）を`conversation`データベースに追加し、`web_backend`が既存の`ConversationDB`（`conversation_db/db.py`）と同一の方式（`psycopg2`による直接SQL、コンテキストマネージャー）で読み書きする。**

- 新規のRDSインスタンス・新規のデータベース・新規のSecrets Managerシークレットは作成しない。既存の`CONVERSATION_DB_URL`（ADR-0044で新設済み）をそのまま使う。
- スキーマ（4テーブルのDDL）は、ローカル`docker-compose`環境では`db_conversation/init.sql`に追加し、AWS環境では既存の`db_hiroba_qa_init`の`conversation`データベース向けスキーマ適用処理（ADR-0044が新設した処理）に追加する。既存の`conversation`/`message`テーブルの適用方式（冪等な`CREATE TABLE IF NOT EXISTS`、yoyoによる履歴管理は導入しない）を踏襲する。
- `web_backend`側には、既存の`conversation_db/`（`models.py`/`db.py`）と並行する新規モジュール`verification_db/`を追加する。既存モジュールへの機能追加（`ConversationDB`クラスの拡張）ではなく、独立した新規モジュールとする（責務の分離。既存の会話履行・評価とスキーマ・ライフサイクルが異なるため）。
- `verification_run_tag.tag_id`・`verification_run_source.source_id`は、`chatbot`データベース側の`tag.id`・`qa_original.uuid`の値をそのまま保持するが、外部キー制約は設定しない。PostgreSQLの外部キー制約は同一データベース内でのみ設定可能であり、`chatbot`データベースと`conversation`データベースを跨いだ参照整合性はアプリケーションレベルでも保証しない（実行当時のスナップショットとして保持することを優先する。要件定義書7.3節）。

## 検討した代替案

- **Knowledge MCPに検証結果保存用の新規ツールを追加し、`chatbot`データベースに保存する**: ADR-0013の「QA・タグの書き込みはKnowledge MCP経由に統一する」という既存方針に最も忠実な案である。しかし、検証結果は「QA・タグそのもの」ではなく、それらを使った実行の記録（会話履行・評価データと同種の運用ログ）であり、Knowledge MCPのドメイン（QAナレッジベースの参照・管理、ADR-0004のMVPスコープ）には本来含まれない。Knowledge MCPに無関係な責務（検証ログの保存）を持たせることになり、同サーバの責務が拡散する。また`chatbot`データベースのスキーマ変更（マイグレーション追加）と`knowledge_mcp`のコード変更の両方が必要になり、変更範囲が本案より大きい。以上より不採用とした。
- **新規の専用データベース（新規RDSインスタンス、またはRDS内の第3のデータベース）を用意する**: QA・会話データとライフサイクルを完全に分離できる利点があるが、ADR-0044が新規RDSインスタンス案を見送った理由（追加コスト、MVPでは過大）がそのまま当てはまる。RDS内に第3のデータベースを追加する案（`conversation`と同様の方式）は技術的には可能だが、`web_backend`から見て新規のデータベース名・接続文字列の管理が増えるだけで、`conversation`データベースに相乗りする案と比べて明確な利点がない。将来、検証データの保持期間・削除ポリシーをQA・会話データと明確に分離する必要が生じた場合に再検討する。
- **`verification_run_tag`/`verification_run_source`を`chatbot`データベースの`tag`/`qa_original`へ外部キー参照する構成**（データベースをまたぐ構成そのものを避けるため、検証データも`chatbot`データベースに置く案の一種）: 参照整合性を保てる利点があるが、`chatbot`データベースはADR-0013によりKnowledge MCP経由でのみ書き込む方針であり、`web_backend`が直接書き込む例外を新設することになる。ADR-0045が`conversation`データベースに限定して認めた「直接アクセスの例外」を`chatbot`データベースにも広げることになり、既存方針との整合性が最も低いため不採用とした。

## 結果・影響

- `web_backend/src/verification_db/`（新規モジュール）が追加される。既存の`conversation_db/`・`mcp_client/`には変更を加えない。
- `db_conversation/init.sql`に4テーブルのDDLが追加される。既存の`conversation`/`message`テーブルの定義には変更を加えない。
- AWS側は、`db_hiroba_qa_init`の`conversation`データベース向けスキーマ適用処理（ADR-0044）に同DDLが追加される。新規のTerraformリソース（RDSインスタンス、Secrets Managerシークレット、セキュリティグループ）は発生しない。`admin_ui_task → rds`の到達性は既存のADR-0045のルールがそのまま使える。
- `chatbot`データベース・Knowledge MCPには変更を加えない。ADR-0013の「QA・タグの書き込みはKnowledge MCP経由」という方針は、検証データがその対象外であることが本ADRにより明確化される（会話履行・評価データがADR-0044/0045で対象外とされたのと同じ扱い）。
- `verification_run_tag`/`verification_run_source`が保持する`tag_id`/`source_id`は、参照先が`chatbot`データベース側で削除・変更されても追随しない（スナップショットとして固定される）。これは「実行当時に実際に返された結果を記録する」という検証機能の目的（要件定義書1章）に対しては望ましい特性だが、「今この`tag_id`は存在するか」をUI側で確認したい場合は、別途Knowledge MCPへの参照確認（`get_qa`等）を組み合わせる必要がある。本フェーズではこの確認機能は実装しない。
