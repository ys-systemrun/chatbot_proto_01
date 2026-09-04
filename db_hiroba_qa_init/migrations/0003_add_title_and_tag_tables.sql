-- IMPL-202608061016 / 統合マイグレーション 0003
-- 旧 knowledge_mcp/migrations/0001_add_title_and_tag_tables.sql 相当。
-- qa_original.title 列と tag / qa_tag テーブル・インデックスを追加する。
-- 冪等（IF NOT EXISTS）。

ALTER TABLE hiroba_qa_original
    ADD COLUMN IF NOT EXISTS title TEXT;

CREATE TABLE IF NOT EXISTS hiroba_tag (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_tag_id INTEGER REFERENCES hiroba_tag(id)
);

CREATE TABLE IF NOT EXISTS hiroba_qa_tag (
    qa_id TEXT NOT NULL REFERENCES hiroba_qa_original(uuid),
    tag_id INTEGER NOT NULL REFERENCES hiroba_tag(id),
    PRIMARY KEY (qa_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_hiroba_qa_tag_tag_id ON hiroba_qa_tag (tag_id);
CREATE INDEX IF NOT EXISTS idx_hiroba_tag_parent_tag_id ON hiroba_tag (parent_tag_id);
