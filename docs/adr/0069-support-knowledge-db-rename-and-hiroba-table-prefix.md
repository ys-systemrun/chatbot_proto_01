# ADR-0069: サポート知識DB基盤化に伴うDB名再編と維津美の広場テーブルへの`hiroba_`接頭辞付与

- ステータス: Accepted
- 日付: 2026-09-01
- 関連: `docs/requirement/202609010935_サポート知識DB基盤化に伴うDB名再編・テーブル接頭辞付与要件定義書.md`, ADR-0016, ADR-0017, ADR-0018, ADR-0026, ADR-0037, ADR-0046, ADR-0047, ADR-0052, ADR-0055, ADR-0066

## コンテキスト

現在のQA/ナレッジ用データベースは、ユーザーサポート「維津美の広場」由来のQAデータという単一データソース専用の構成である。発注者は今後、維津美の広場とは異なるデータソースを追加し、PostgreSQL上でデータソースごとに実データベースを分離して、それぞれ独立したマイグレーション・シーディング機構で管理する方針を示した。この将来像に向けて、単一データソース前提の命名を「複数データソースDBを載せる基盤サーバ＋データソース別の実DB」という構造へ再編する必要がある。

リポジトリ調査の結果、「`db_hiroba_qa`」という語は3つの別物を指していることが判明した。(1) docker-composeのサービス名かつ接続ホスト名、(2) 初期化サービス/ディレクトリ `db_hiroba_qa_init`、そして実際のPostgreSQLデータベース名は (3) `chatbot` である（接続文字列は `…@db_hiroba_qa:5432/chatbot`）。AWSでは実DB名はterraform `var.db_name`（既定`"chatbot"`）で、RDSの初期データベースとして作成される。

対象6テーブル（`category`/`qa_original`/`tag`/`question_altered`/`tag_alias`/`qa_tag`）のテーブル名は、中央集約された定数モジュールを持たず、`db_hiroba_qa_init`のmigration/seed、`knowledge_mcp`の各リポジトリSQL、`web_backend`のエクスポート定義（`export/tables.py`）と`db.py`、`tag_selector_mcp`のタグメタデータ取得SQL、および各テスト（SQL部分文字列で分岐する`FakeDatabase`を含む）に、インラインのリテラルとしてハードコードされている。したがって命名変更はシステム横断の一括変更であり、部分適用は旧名参照の残存という不整合を生む。

エクスポート済みの `terraform/chatbot.sql`（6150行）は `pg_dump` ではなく `web_backend` のエクスポート機能が生成する `CREATE TABLE IF NOT EXISTS` + `INSERT INTO "…" VALUES` 形式のスクリプトで、DB名・`CREATE DATABASE`・`\connect`・`GRANT`・`CREATE ROLE` を一切含まない。発注者は、このダンプを新命名に変換し、terraformで基盤を作り直したあとそのまま再インポートして復元できる状態にすることを要求している。またマイグレーション方式はyoyo（ADR-0017）であり、適用管理はファイル名stemで行われるため、既存migrationファイルの書き換えは既適用DBでは再実行されず、`IF NOT EXISTS`により旧名テーブルの隣に空の新名テーブルが二重生成される罠がある。

## 決定

**PostgreSQLサーバ（＝docker-composeサービス/ホスト名）を`db_hiroba_qa`→`db_support_knowledge`、維津美の広場由来データの実データベース名を`chatbot`→`db_hiroba_qa`にリネームし、維津美の広場由来6テーブルに`hiroba_`接頭辞を付与する。`chatbot`を冠する識別子（ロール・シークレット・環境変数名・ダンプファイル名・定数名）はその名称を据え置き、変更するのはDB名の値とテーブル接頭辞に限定する。既存DBは無停止改名せず、terraformでの再構築＋変換済み`chatbot.sql`の再インポートで移行する。API/UI名も新テーブル名に追随させる。**

1. **3層の命名再編**: サーバ/サービス/ホスト名 `db_hiroba_qa`→`db_support_knowledge`（複数データソースDBを載せる基盤）、実DB名 `chatbot`→`db_hiroba_qa`（維津美の広場由来データ専用DB）、6テーブルへの `hiroba_` 接頭辞付与（`hiroba_category`/`hiroba_qa_original`/`hiroba_tag`/`hiroba_question_altered`/`hiroba_tag_alias`/`hiroba_qa_tag`）。実DB名とテーブル接頭辞が二重に維津美の広場を示す冗長性は、データソースの分離単位（DB）と出自（接頭辞）を独立に明示する意図として受容する。

2. **`chatbot`冠識別子の据え置き**: ロール（`chatbot_app`/`chatbot_migrator`）・シークレット（`chatbot_app_db_url`等）・環境変数名（`CHATBOT_*`）・ダンプファイル名（`chatbot.sql`）・定数名（`CHATBOT_TABLES`）の名称は変更しない。`CHATBOT_DB_NAME` の値のみ `chatbot`→`db_hiroba_qa` とする。名称の全面的な `support_knowledge` 系への統一は影響範囲が大きく、DB名再編の目的達成には不要なため今回のスコープに含めない。

3. **テーブル名の全出現箇所の一括変更**: `db_hiroba_qa_init`（migrations 0001〜0005・`db.py`・`backfill_title_and_tags.py`・`seed_description_and_aliases.py`・`import_data.py`の`CHATBOT_TABLES`・`tests`）、`knowledge_mcp`（4リポジトリ・4テスト）、`web_backend`（`db.py`・`export/tables.py`・`export_controller.py`）、`tag_selector_mcp`（`tag_metadata_repository.py`）を同一マッピングで更新する。`export/dump.py` は `spec.name` 経由の汎用実装のため変更しない。列名（`tag_id`/`qa_id`/`parent_tag_id`/`category_id`）・CTEエイリアス`tag_closure`・yoyo管理テーブル・conversation系テーブルは改名対象から除外する（構文限定置換）。

4. **`chatbot.sql`の構文限定変換と恒久対応の分離**: 既存ダンプは `CREATE TABLE <name>`・`INSERT INTO "<name>"`・`REFERENCES <name>(…)` の3パターンのみを新テーブル名へ置換し、列名・値・埋め込みデータは不変とする（DB名の変更は不要＝ダンプはDB名非依存）。恒久対応は `web_backend/src/export/tables.py` の更新に置き、以後のエクスポートが新命名の `chatbot.sql` を自動生成するようにする。ダンプ変換は一度きりの移行措置と位置づける。

5. **移行は再構築＋再インポート方式**: 既存DBを無停止改名する `ALTER TABLE … RENAME` マイグレーション（例: `0006_rename_*`）は作成せず、既存migrationファイルを新テーブル名で書き換える。ローカルはボリューム破棄による作り直し、AWSはDB用stateレイヤ（ADR-0037）の destroy+apply による再構築とし、いずれも空DBから新命名で初期化したうえで変換済み `chatbot.sql` を全データインポート経路（ADR-0055/0066）で投入する。yoyoのファイル名stem管理と `IF NOT EXISTS` 冪等性の性質上、旧名テーブルが残るDBへ新名DDLを適用すると二重生成が起きるため、作り直し（空DB）を移行の前提条件とする。

6. **サーバ名リネームのローカル限定性**: サーバ/ホスト名 `db_hiroba_qa`→`db_support_knowledge` はローカル docker-compose の変更（サービス名・`DATABASE_URL`ホスト部・`depends_on`・`POSTGRES_DB`）に限定する。AWSでは接続ホストはRDSエンドポイントであり `db_hiroba_qa` というホスト名は存在しないため、AWS側で必須なのは `var.db_name` の変更のみとする。RDSリソース名/タグの整合は任意（機能非影響）とする。

7. **API/UI名の追随**: DB層のテーブル改名にとどめず、対応するHTTP APIパス・応答フィールド名・`front_dev`のルート/`api.ts`/feature/domain を新命名へ揃える。HTTP契約変更を伴うためバックエンドとフロントエンドを同時更新する。`hiroba_`接頭辞をAPI/UIへどこまで露出させるか（内部識別子のみか表示名も含むか）の具体的対応表は詳細設計フェーズで確定する。

## 検討した代替案

- **実DB名を`chatbot`のまま維持し、サーバ名とテーブル接頭辞のみ変更する**: 変更範囲は最小になる。しかし発注者の「データソースごとに実DBを分離し、異なるマイグレーション・シード機構で管理する」という将来像において、維津美の広場DBが汎用名`chatbot`のままでは新ソースDBとの対比で出自が不明瞭になる。発注者が実DB名の`db_hiroba_qa`への変更を明示的に要望したため不採用とした。

- **実DB名を`db_`接頭辞なしの`hiroba_qa`とする**: 「`db_`はサーバ名側の接頭辞」と整理すれば命名の重複感は下がる。しかし発注者確認により実DB名は`db_hiroba_qa`で確定したため不採用とした（Open Issueとして提示したうえでの決定）。

- **既存DBを`ALTER TABLE … RENAME`で無停止改名するマイグレーション（`0006_rename_*`）を追加する**: 稼働中DBを破棄せず改名でき、AWSのRDSインスタンス置換も回避できる利点がある。しかし発注者は「terraformで作り直して再インポート」という運用を明示し、ダンプからの完全復元を前提としたため、二重の移行経路（改名マイグレーション＋作り直し）を持たず作り直し方式に一本化した。無停止改名が必要になった場合は別途この案を要件化する。

- **RDSインスタンス置換を避けるため、実DB `db_hiroba_qa` を初期化コンテナの`CREATE DATABASE`で作成する（会話DB `conversation` と同方式、RDS初期DB名は中立値に据え置く）**: RDSインスタンスを再作成せずに新DBを追加でき、将来の複数ソースDB（各ソースを`CREATE DATABASE`で追加）という基盤像とも整合する。一方で、現在RDSの初期DBとして作成されている`chatbot`の作成責務を初期化コンテナ側へ移す再設計が必要になり、既存の空DBが残る等の過渡的な複雑さを伴う。発注者が「作り直し」を許容し、かつ本ADRのスコープを命名再編に集中させるため、今回は採用しない。ただしRDS置換の停止影響が運用上許容できない場合の有力な代替として要件定義書のOpen Issue #1に記録する。

- **`chatbot`冠の全識別子（ロール・シークレット・環境変数・ファイル名・定数）も`support_knowledge`系へ統一する**: 命名の一貫性は最大化する。しかしロール名・シークレット名・環境変数名の変更はterraform・deployスクリプト・全サービス設定に大量の変更を波及させ、DB名再編という目的の達成には不要である。発注者が据え置きを選択したため不採用とし、将来の統一は別要件とする（要件定義書Open Issue #4）。

- **`chatbot.sql`を単純な全文字列置換（`s/tag/hiroba_tag/`等）で変換する**: 実装は容易だが、`tag_id`・`parent_tag_id`・`qa_id`・`category_id`等の列名やCTEエイリアス`tag_closure`、`qa_tag`/`tag_alias`という短い部分一致を巻き込み、データを破壊する。テーブル名として現れる構文パターン（`CREATE TABLE`/`INSERT INTO "…"`/`REFERENCES …(`）に限定した置換とし、変換前後の件数一致（CREATE TABLE 6・INSERT総ブロック・FK 4）で検証する方式を採用した。

## 結果・影響

- 3層のリネームがシステム横断で行われる。`db_hiroba_qa_init`・`knowledge_mcp`・`web_backend`・`tag_selector_mcp`・`front_dev`・`docker-compose.yml`・`terraform`（`chatbot.sql`・`var.db_name`）・`README.md`・`.env.example` が変更対象となる。`front_dev` はDB非依存だが、API/UI名追随方針（決定7）により追随変更が生じる。
- `web_backend/src/export/tables.py` の更新により、以後のエクスポートは新テーブル名の `chatbot.sql`/CSV を自動生成する。`export/dump.py`・モデルdataclassは変更不要。
- `db_hiroba_qa_init` の `CHATBOT_TABLES`（`import_data.py`）と `web_backend/src/export/tables.py` のテーブル一覧は同期が必須であり、齟齬があると全データインポート（ADR-0066）が壊れる。テスト（`test_import_data.py`）の期待一覧・シーケンス名（`public.tag_id_seq`→`public.hiroba_tag_id_seq`）も追随する。
- AWSでは `var.db_name` 変更がRDS初期DB名の変更＝`aws_db_instance`の置換を伴い、DB用stateレイヤの再構築（ADR-0037）が必要になる。同一RDSインスタンス上の会話DB（`conversation`）も再作成対象となるため、`conversation.sql` の再投入を含む復旧手順を運用計画として確定する（要件定義書Open Issue #1）。会話DBの命名自体は変更しない。
- 既存の役割分離（ADR-0052: migrator/app、ADR-0046: export専用reader）は、ロール名を据え置いたままDB名 `db_hiroba_qa` に対して再設定される。権限体系・ロール名は不変。
- conversation系テーブル（`conversation`/`message`/`verification_*`）は `hiroba_` 接頭辞の対象外。`verification_run_source` はタグ名をJSON文字列で保持しFKを持たないため、テーブル改名の影響を受けない。
- `chatbot` を冠する識別子の名称が据え置かれる結果、「実DBは `db_hiroba_qa` だが、それを扱うロール/環境変数/ダンプは `chatbot_*`/`CHATBOT_*`/`chatbot.sql`」という名称の不一致が残る。これは意図的な割り切りであり、将来の統一は別途要件化する（要件定義書Open Issue #4）。
- 監査ログのエンティティ種別ラベル・index名/シーケンス名の命名規約・API/UIへの `hiroba_` 露出範囲は、詳細設計フェーズで確定する未決事項として残る（要件定義書Open Issue #2/#3/#5）。
