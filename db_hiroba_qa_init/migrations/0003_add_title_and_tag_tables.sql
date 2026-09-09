-- IMPL-202608061016 / 統合マイグレーション 0003
-- 旧 knowledge_mcp/migrations/0001_add_title_and_tag_tables.sql 相当。
-- qa_original.title 列と tag / qa_tag テーブル・インデックスを追加する。
-- 冪等（IF NOT EXISTS）。
-- ADR-0077: 共有タグマスタを中立名称 tag へ改名（データソース非依存の共有マスタであることを
-- 名称面でも明示する）。維津美の広場QA側の結合テーブル hiroba_qa_tag は改名せず、その tag_id
-- 外部キーの参照先のみ tag(id) とする。

ALTER TABLE hiroba_qa_original
    ADD COLUMN IF NOT EXISTS title TEXT;

CREATE TABLE IF NOT EXISTS tag (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_tag_id INTEGER REFERENCES tag(id)
);

CREATE TABLE IF NOT EXISTS hiroba_qa_tag (
    qa_id TEXT NOT NULL REFERENCES hiroba_qa_original(uuid),
    tag_id INTEGER NOT NULL REFERENCES tag(id),
    PRIMARY KEY (qa_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_hiroba_qa_tag_tag_id ON hiroba_qa_tag (tag_id);
CREATE INDEX IF NOT EXISTS idx_tag_parent_tag_id ON tag (parent_tag_id);
