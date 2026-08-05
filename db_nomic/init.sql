CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS qa_original (
    uuid TEXT PRIMARY KEY,
    question_text TEXT,
    answer_text TEXT,
    category_id INTEGER,
    title TEXT
);

CREATE TABLE IF NOT EXISTS question_altered (
    id SERIAL PRIMARY KEY,
    qa_id TEXT,
    text TEXT,
    embedding VECTOR(768)
);

CREATE TABLE IF NOT EXISTS category (
    id INTEGER PRIMARY KEY,
    name TEXT
);

-- IMPL-202608041013 / ADR-0005: タグは関連テーブルで表現する。
-- parent_tag_id は将来のツリー構造対応のための列で、MVP時点では全レコード NULL のまま投入する。
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



-- embedding VECTOR(384) はモデルに合わせ変更