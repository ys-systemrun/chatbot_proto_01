# db_init/migrations — knowledge データベースのマイグレーション

knowledge データベース（`db_chatbot_knowledge_base`）のスキーマを yoyo で順に適用するマイグレーションです（ADR-0017）。
`db_init/src/main.py` が migrator ロールの接続で適用します（ADR-0052）。各ステップは `IF NOT EXISTS` 等で冪等です。
embedding 列の次元数が環境（埋め込みモデル）に依存するステップは、環境変数 `EMBEDDING_VECTOR_DIM` を読む Python ステップにしています。

## 構成

| 名前 | 説明 |
|---|---|
| [`0001_initial_schema.sql`](0001_initial_schema.sql) | 基礎スキーマ。`vector` 拡張、`hiroba_qa_original`（title を含まない基礎形）、カテゴリ `hiroba_category`（旧 `db_nomic/init.sql` 相当） |
| [`0002_question_altered_table.py`](0002_question_altered_table.py) | 言い換え質問文テーブル `hiroba_question_altered` を作成。`VECTOR(N)` の N を `EMBEDDING_VECTOR_DIM` から組み立てる |
| [`0003_add_title_and_tag_tables.sql`](0003_add_title_and_tag_tables.sql) | `hiroba_qa_original.title` 列と、共有タグマスタ `tag`・結合テーブル `hiroba_qa_tag` を追加（ADR-0077 で `tag` に改名） |
| [`0004_add_question_altered_is_primary.sql`](0004_add_question_altered_is_primary.sql) | `hiroba_question_altered.is_primary` 列を追加（QA 作成時の主質問文行を識別） |
| [`0005_add_tag_description_and_alias.sql`](0005_add_tag_description_and_alias.sql) | `tag.description` 列と同義語テーブル `tag_alias` を追加（ADR-0008） |
| [`0006_add_tag_folder.sql`](0006_add_tag_folder.sql) | 表示専用の分類フォルダ `tag_folder` と `tag.folder_id` を追加（ADR-0072） |
| [`0007_add_tag_folder_hierarchy.sql`](0007_add_tag_folder_hierarchy.sql) | `tag_folder.parent_folder_id` を追加してフォルダをツリー化し、フォルダ名の一意制約を撤廃（ADR-0073） |
| [`0008_add_tag_display_order.sql`](0008_add_tag_display_order.sql) | `tag`・`tag_folder` に兄弟内の表示順 `display_order` を追加し、既存行に初期値を採番（ADR-0074） |
| [`0009_add_troubleshooting_article_tables.py`](0009_add_troubleshooting_article_tables.py) | トラブルシューティング記事 `troubleshooting_article` と `troubleshooting_article_tag` を作成（ADR-0076）。embedding 次元は 0002 と同じく環境変数から |
| [`0010_add_is_searchable.sql`](0010_add_is_searchable.sql) | 情報源レコードの検索対象フラグ `is_searchable`（既定 true）を QA・言い換え・トラブルシューティング記事の3テーブルに追加（ADR-0092） |
