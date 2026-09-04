CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS hiroba_qa_original (
    uuid TEXT PRIMARY KEY,
    question_text TEXT,
    answer_text TEXT,
    category_id INTEGER
);

CREATE TABLE IF NOT EXISTS hiroba_question_altered (
    id SERIAL PRIMARY KEY,
    qa_id TEXT,
    text TEXT,
    embedding VECTOR(384)
);

CREATE TABLE IF NOT EXISTS hiroba_category (
    id INTEGER PRIMARY KEY,
    name TEXT
);

-- embedding VECTOR(384) はモデルに合わせ変更