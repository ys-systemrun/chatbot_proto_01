# db_init/migrations_conversation — conversation データベースのマイグレーション

knowledge とは独立した conversation データベースのスキーマを yoyo で適用するマイグレーションです（ADR-0051）。
`db_init/src/main.py` がロール作成の後に適用します。各ステップは冪等（`IF NOT EXISTS`）です。

## 構成

| 名前 | 説明 |
|---|---|
| [`0001_initial_conversation_message.sql`](0001_initial_conversation_message.sql) | 会話 `conversation` とメッセージ `message` のテーブル（旧 `db_conversation/init.sql` をそのまま移植） |
| [`0002_add_verification_tables.sql`](0002_add_verification_tables.sql) | 検証機能（質問 → タグ → 情報源の検索精度検証, ADR-0048）の4テーブル `verification_question`・`verification_run`・`verification_run_tag`・`verification_run_source` |
| [`0003_add_verification_existing_tags.sql`](0003_add_verification_existing_tags.sql) | 検証の入力に既存タグを追加（`verification_question.existing_tags`・`verification_run.existing_tags_snapshot`, ADR-0060） |
| [`0004_add_release_and_evaluation_comment.sql`](0004_add_release_and_evaluation_comment.sql) | 回答を生成したリリース・方式（`message.release_id`・`ask_mode`）、評価の理由と日時、リリース表 `release` を追加（ADR-0099 段階①） |
