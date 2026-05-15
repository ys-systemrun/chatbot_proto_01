CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE qa (
    id SERIAL PRIMARY KEY,
    uuid TEXT,
    question TEXT,
    answer TEXT,
    embedding VECTOR(768)
);

-- embedding VECTOR(384) はモデルに合わせ変更