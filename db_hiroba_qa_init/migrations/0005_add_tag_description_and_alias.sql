-- IMPL-202608061016 / 統合マイグレーション 0005
-- 旧 tag_selector_mcp/migrations/0001_add_tag_description_and_alias.sql 相当。
-- tag.description 列と tag_alias 関連テーブル・インデックスを追加する（ADR-0008）。
-- 冪等（IF NOT EXISTS）。
-- ADR-0077: 共有タグマスタを中立名称 tag / tag_alias へ改名。

ALTER TABLE tag
    ADD COLUMN IF NOT EXISTS description TEXT;

CREATE TABLE IF NOT EXISTS tag_alias (
    id SERIAL PRIMARY KEY,
    tag_id INTEGER NOT NULL REFERENCES tag(id),
    alias TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_tag_alias_tag_id ON tag_alias (tag_id);
