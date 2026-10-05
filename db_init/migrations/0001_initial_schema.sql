-- IMPL-202608061016 / 統合マイグレーション 0001
-- モデル非依存の基礎スキーマ（現行 db_nomic/init.sql の該当部分を統合）。
-- CREATE EXTENSION vector, qa_original（title を含まない基礎形）, category。
-- title 列・tag/qa_tag/tag_alias・is_primary・description は後続ステップで追加する
--（既存の手動マイグレーション順序をそのまま単一履歴へ統合するため）。
-- 冪等（IF NOT EXISTS）なので、既に適用済みの環境で再実行しても無害。

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS hiroba_qa_original (
    uuid TEXT PRIMARY KEY,
    question_text TEXT,
    answer_text TEXT,
    category_id INTEGER
);

CREATE TABLE IF NOT EXISTS hiroba_category (
    id INTEGER PRIMARY KEY,
    name TEXT
);
