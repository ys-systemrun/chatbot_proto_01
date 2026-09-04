-- IMPL-202608061016 / 統合マイグレーション 0005
-- 旧 tag_selector_mcp/migrations/0001_add_tag_description_and_alias.sql 相当。
-- tag.description 列と tag_alias 関連テーブル・インデックスを追加する（ADR-0008）。
-- 冪等（IF NOT EXISTS）。

ALTER TABLE hiroba_tag
    ADD COLUMN IF NOT EXISTS description TEXT;

CREATE TABLE IF NOT EXISTS hiroba_tag_alias (
    id SERIAL PRIMARY KEY,
    tag_id INTEGER NOT NULL REFERENCES hiroba_tag(id),
    alias TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_hiroba_tag_alias_tag_id ON hiroba_tag_alias (tag_id);
