-- IMPL-202608261022 / ADR-0051 conversation マイグレーション 0002
-- 検証機能（質問→タグ→情報源の検索精度検証, ADR-0048 / IMPL-202608260909 5.1 節）の4テーブル。
-- conversation データベース上に配置する。tag_id / source_id は chatbot データベース側の値を
-- 参照するが、データベースを跨ぐ外部キー制約は張らない（ADR-0048 / 10章）。
-- path（verification_run_tag）/ metadata（verification_run_source）は JSON 文字列を TEXT に保存する。
-- 冪等（CREATE TABLE IF NOT EXISTS）。

CREATE TABLE IF NOT EXISTS verification_question (
    id             SERIAL PRIMARY KEY,
    question_text  TEXT NOT NULL,
    memo           TEXT,
    created_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS verification_run (
    id                        SERIAL PRIMARY KEY,
    question_id               INTEGER NOT NULL REFERENCES verification_question(id) ON DELETE CASCADE,
    question_text_snapshot    TEXT NOT NULL,
    executed_at               TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status                    VARCHAR NOT NULL,
    error_message             TEXT,
    max_tags                  INTEGER,
    confidence_threshold      REAL,
    top_k                     INTEGER,
    min_score                 REAL,
    tag_selector_latency_ms   INTEGER,
    knowledge_mcp_latency_ms  INTEGER,
    evaluation                SMALLINT,
    evaluation_comment        TEXT,
    evaluated_at              TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS verification_run_tag (
    id        SERIAL PRIMARY KEY,
    run_id    INTEGER NOT NULL REFERENCES verification_run(id) ON DELETE CASCADE,
    rank_no   INTEGER NOT NULL,
    tag_id    INTEGER,
    tag_name  VARCHAR NOT NULL,
    score     REAL,
    path      TEXT
);

CREATE TABLE IF NOT EXISTS verification_run_source (
    id           SERIAL PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES verification_run(id) ON DELETE CASCADE,
    rank_no      INTEGER NOT NULL,
    source_id    VARCHAR,
    source_type  VARCHAR,
    title        TEXT,
    content      TEXT,
    score        REAL,
    metadata     TEXT
);
