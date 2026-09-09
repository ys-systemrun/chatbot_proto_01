CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS hiroba_qa_original (
    uuid TEXT PRIMARY KEY,
    question_text TEXT,
    answer_text TEXT,
    category_id INTEGER,
    title TEXT
);

-- IMPL-202608060837 / T1: is_primary は create_qa が生成する主質問文行を識別する
-- （update_qa は is_primary=true の1件のみ再計算し、既存パラフレーズ行を保護する）。
CREATE TABLE IF NOT EXISTS hiroba_question_altered (
    id SERIAL PRIMARY KEY,
    qa_id TEXT,
    text TEXT,
    embedding VECTOR(768),
    is_primary BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS hiroba_category (
    id INTEGER PRIMARY KEY,
    name TEXT
);

-- IMPL-202608041013 / ADR-0005: タグは関連テーブルで表現する。
-- parent_tag_id は将来のツリー構造対応のための列で、MVP時点では全レコード NULL のまま投入する。
-- IMPL-202608051712 / ADR-0008: description カラムは Tag Selector MCP のタグ選択で用いる。
CREATE TABLE IF NOT EXISTS tag (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_tag_id INTEGER REFERENCES tag(id),
    description TEXT
);

CREATE TABLE IF NOT EXISTS hiroba_qa_tag (
    qa_id TEXT NOT NULL REFERENCES hiroba_qa_original(uuid),
    tag_id INTEGER NOT NULL REFERENCES tag(id),
    PRIMARY KEY (qa_id, tag_id)
);

-- IMPL-202608051712 / ADR-0008: 同義語は配列カラムではなく tag_alias 関連テーブルで表現する。
CREATE TABLE IF NOT EXISTS tag_alias (
    id SERIAL PRIMARY KEY,
    tag_id INTEGER NOT NULL REFERENCES tag(id),
    alias TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_hiroba_qa_tag_tag_id ON hiroba_qa_tag (tag_id);
CREATE INDEX IF NOT EXISTS idx_tag_parent_tag_id ON tag (parent_tag_id);
CREATE INDEX IF NOT EXISTS idx_tag_alias_tag_id ON tag_alias (tag_id);



-- embedding VECTOR(384) はモデルに合わせ変更