-- IMPL-202608041013 / T2
-- 既存 chatbot_db に title 列 + tag / qa_tag テーブルを追加するマイグレーション。
-- 稼働中DBには init.sql が再実行されないため、本SQLを個別に適用する（実装指示書4.2節）。
--   docker compose exec db psql -U postgres -d chatbot -f /path/to/0001_add_title_and_tag_tables.sql
-- 冪等（IF NOT EXISTS）なので複数回適用しても安全。

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
