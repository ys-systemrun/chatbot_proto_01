-- IMPL-202608061016 / 統合マイグレーション 0004
-- 旧 knowledge_mcp/migrations/0002_add_question_altered_is_primary.sql 相当。
-- question_altered に is_primary 列を追加する（create_qa の主質問文行を識別するため）。
-- 冪等（ADD COLUMN IF NOT EXISTS）。

ALTER TABLE hiroba_question_altered
    ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT false;
