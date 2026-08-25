# ADR-0046: chatbotデータベースのエクスポート専用読み取り経路の新設（ADR-0013・ADR-0041の限定的な見直し）

- ステータス: Accepted
- 日付: 2026-08-24
- 関連: `docs/requirement/202608241530_全データエクスポート機能要件定義書.md`, ADR-0005, ADR-0006, ADR-0013, ADR-0026, ADR-0041, ADR-0044, ADR-0045

## コンテキスト

`docs/requirement/202608241530_全データエクスポート機能要件定義書.md` にて、`admin_ui`（`front_dev` + `web_backend`）にボタン一つで本プロジェクトが扱う全データ（`chatbot` データベースの `qa_original` / `question_altered` / `category` / `tag` / `tag_alias` / `qa_tag`、および `conversation` データベースの `conversation` / `message`）をSQLまたはCSVとしてエクスポートする機能を追加する要件を整理した。

`conversation` データベースについては、ADR-0044・ADR-0045により `admin_ui` が `CONVERSATION_DB_URL` を用いて直接読み書きする経路が既に存在するため、エクスポート機能もこの既存経路をそのまま読み取りに使えばよい。

一方 `chatbot` データベースは、次の2つの既存決定により `admin_ui` から直接アクセスできない。

- ADR-0013: `web_backend` に新設するQA・タグ管理系API（`/api/qa/*`, `/api/tags/*`, `/api/categories`）は `chatbot` データベースへ直接アクセスせず、すべてKnowledge MCPサーバのMCPツール経由とする。タグの循環参照チェック等の業務ロジックをKnowledge MCPに一本化し、二重実装による仕様乖離を避けるための決定である。
- ADR-0041 / ADR-0045: AWS上の `admin_ui` には `chatbot` データベースの資格情報（`DATABASE_URL`）を注入しない。`admin_ui` に付与するのは `conversation` データベース専用の資格情報（`CONVERSATION_DB_URL`）のみとし、これによりアプリケーションレベル（資格情報スコープ）で `chatbot` データベースへの到達を防いでいる。

今回のエクスポート機能は、`qa_original` 等6テーブルの全行・全カラム（`question_altered.embedding` の埋め込みベクトルを含む）をそのままの形でダンプする必要があり、これはKnowledge MCPが既に提供している `list_qa` / `list_tags` / `list_categories` 等の管理系ツール（UI表示用に整形・ページングされ、`embedding` 列のような内部表現を含まない）では代替できない。かといって、Knowledge MCPに「生テーブルを丸ごと返す」新規ツールを追加する案は、ADR-0006が定めた「Knowledge MCPは業務ロジック（タグ階層検証等）を担うレイヤーである」という位置づけと整合しない、汎用ダンププロキシ化のリスクを抱える。

したがって、本ADRでは `chatbot` データベースについて、既存の書き込み経路（ADR-0013）とは別に、**エクスポート専用の読み取り専用アクセス経路**を新設するかどうかを決定する。

## 決定

**`chatbot` データベースに、エクスポート専用の読み取り専用PostgreSQLロールを新設し、`admin_ui` にこのロール用の資格情報のみを新たに注入する。既存のQA・タグ登録編集の書き込み経路（Knowledge MCP経由、ADR-0013）は変更しない。**

1. **読み取り専用ロールの新設**: `chatbot` データベースに `chatbot_export_reader` ロールを新設する。付与する権限は次に限定する。
   - `GRANT CONNECT ON DATABASE chatbot TO chatbot_export_reader;`
   - `GRANT USAGE ON SCHEMA public TO chatbot_export_reader;`
   - `GRANT SELECT ON ALL TABLES IN SCHEMA public TO chatbot_export_reader;`
   - `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO chatbot_export_reader;`（今後のマイグレーションで追加されるテーブルにも自動的にSELECTが及ぶようにする）
   - `INSERT` / `UPDATE` / `DELETE` / DDL権限は一切付与しない。
   - 防御的多重化として、`conversation` データベースへの `CONNECT` 権限は明示的に付与しない（同一RDSインスタンス上の別データベースであるため、テーブル権限がなくとも接続自体が可能にならないよう `REVOKE CONNECT ON DATABASE conversation FROM chatbot_export_reader;` も併せて実行する）。
2. **ロール作成の実行主体**: 既存の `db_hiroba_qa_init`（ADR-0016〜0018のワンショットマイグレーション・シードサービス）の起動シーケンスに、上記ロール作成・権限付与ステップを追加する。`CREATE ROLE IF NOT EXISTS` 相当の存在チェックを行い、既存のマイグレーション・シード処理と同様の冪等性（ADR-0018）を維持する。パスワードは新規発行し、Secrets Managerで管理する（実装フェーズで確定）。
3. **資格情報の伝播（AWS）**: `terraform/modules/database` に、`conversation_db_url_secret_arn`（ADR-0044）と同様の形式で `chatbot_export_db_url_secret_arn`（ホスト・ポートは既存 `chatbot` 用と同一、ユーザー・パスワードのみ異なる）を追加する。`terraform/main/app/main.tf` の `module "admin_ui"` に、secrets `CHATBOT_EXPORT_DB_URL` として追加する。
4. **ネットワーク**: 追加のセキュリティグループルールは不要とする。ADR-0045により `admin_ui_task → rds`（5432番）の到達性は既に許可済みであり、本ADRはデータベース内部のロール・権限（アプリケーションレベルの制御）のみを追加する。同一ポートに対して複数のデータベース・ロールが存在する状況は、ADR-0045が既に許容し「資格情報スコープで緩和する」と明言した設計方針と同一線上にある。
5. **ローカル `docker-compose` 環境への影響**: ローカルでは `web_backend` は既に `DATABASE_URL`（`chatbot` データベース、`postgres` 公式イメージのデフォルト権限）を保持しており、この資格情報は元々読み書き可能である。ローカル環境向けに `chatbot_export_reader` 相当の別ロールを新設する運用上の必要性は薄いため、**ローカル環境ではエクスポート機能も既存の `DATABASE_URL` をそのまま流用する**。読み取り専用ロールの新設はAWS環境（`admin_ui` サービス）に限定した対応とする。
6. **既存の書き込み経路は変更しない**: QA・タグの登録・編集・削除（`/api/qa/*`, `/api/tags/*`）は、引き続きKnowledge MCP経由（ADR-0013）に統一する。本ADRが新設するのは読み取り専用・エクスポート専用の経路のみであり、`admin_ui` から `chatbot` データベースへの書き込みを許可するものではない。

## 検討した代替案

- **Knowledge MCPに全テーブルダンプ用の新規ツール（例: `export_qa_data`）を追加し、`admin_ui` はMCPクライアント経由で全行を取得する**: ADR-0013の既存原則（Knowledge MCP経由への統一）を崩さずに済む利点があるが、Knowledge MCPが本来担う「業務ロジックのレイヤー」（ADR-0006）から外れた汎用データダンプ機能を持ち込むことになる。また、`embedding`（768/1536次元の浮動小数点配列）を含む数千行規模のペイロードをMCPのツール呼び出し（JSON-RPCベース）でやり取りするのは、逐次ページングの実装コストや呼び出し回数の増加を招き、素直なSQL/CSV生成に対してオーバーヘッドが大きい。将来Knowledge MCPの役割を「データアクセス全般のゲートウェイ」に広げる方針転換を伴わない限り、採用しないこととした。
- **`admin_ui` に `chatbot` データベースの既存マスター相当の資格情報（Knowledge MCPが使うものと同一の `DATABASE_URL`）をそのまま追加で注入する**: 実装は最も簡単だが、最小権限の原則に反し、ADR-0045が既に指摘した「`admin_ui` が技術的に `chatbot` データベース全体へ到達可能になる残存リスク」を、書き込み権限つきでさらに悪化させる。エクスポート機能に書き込み権限は不要であるため不採用とした。
- **オフラインバッチ（ECS Exec等での一時タスク実行）としてエクスポートを実装し、ブラウザボタンを設けない**: 発注者の要求（ブラウザのボタンクリックで完結させる）に反するため不採用とした。

## 結果・影響

- `db_hiroba_qa_init` にロール作成・権限付与ステップの追加実装が発生する（実装指示書で詳細を指示する）。
- `terraform/modules/database` に `chatbot_export_db_url_secret_arn` 出力が追加され、`terraform/main/database/main.tf` ・ `terraform/main/app/main.tf` を通じて `admin_ui` の secrets（`CHATBOT_EXPORT_DB_URL`）として伝播する変更が必要になる。
- `admin_ui` は `chatbot` データベースに対して読み取り専用の到達性を持つようになる。書き込み経路（Knowledge MCP経由、ADR-0013）は変更されないため、QA・タグの登録編集における業務ロジックの二重実装リスクは生じない。
- ADR-0045が残した「`admin_ui` がRDSインスタンス全体へネットワーク到達可能である」という残存リスクの性質は変わらないが、本ADRにより `chatbot` データベースに対しても資格情報スコープ（読み取り専用ロール）での緩和が追加される。将来、ネットワークレベルでもデータベースごとに分離したい場合はADR-0044「検討した代替案」（RDSインスタンス分離）を再検討する。
- ローカル `docker-compose` 環境には変更を加えない（既存 `DATABASE_URL` を流用するため）。
