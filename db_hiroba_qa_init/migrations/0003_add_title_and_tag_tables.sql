-- IMPL-202608061016 / 統合マイグレーション 0003
-- 旧 knowledge_mcp/migrations/0001_add_title_and_tag_tables.sql 相当。
-- qa_original.title 列と tag / qa_tag テーブル・インデックスを追加する。
-- 冪等（IF NOT EXISTS）。

ALTER TABLE qa_original
    ADD COLUMN IF NOT EXISTS title TEXT;

CREATE TABLE IF NOT EXISTS tag (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_tag_id INTEGER REFERENCES tag(id)
);

CREATE TABLE IF NOT EXISTS qa_tag (
    qa_id TEXT NOT NULL REFERENCES qa_original(uuid),
    tag_id INTEGER NOT NULL REFERENCES tag(id),
    PRIMARY KEY (qa_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_qa_tag_tag_id ON qa_tag (tag_id);
CREATE INDEX IF NOT EXISTS idx_tag_parent_tag_id ON tag (parent_tag_id);
