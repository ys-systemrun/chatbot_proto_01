-- conversation データベースのスキーマ定義（参照用）。
-- IMPL-202608261022 / ADR-0051 以降、スキーマ適用は db_hiroba_qa_init の yoyo
-- （db_hiroba_qa_init/migrations_conversation/）に一元化し、docker-compose の
-- init.sql マウントは廃止した。本ファイルは既存ボリューム互換・スキーマの参照用として
-- 最新形（6テーブル）を保持する。内容は migrations_conversation/0001・0002 と一致させること。

CREATE TABLE IF NOT EXISTS conversation (
    id          VARCHAR PRIMARY KEY,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS message (
    id              VARCHAR PRIMARY KEY,
    conversation_id VARCHAR NOT NULL REFERENCES conversation(id),
    "order"         INTEGER NOT NULL,
    role            SMALLINT NOT NULL,
    evaluation      SMALLINT,
    input           TEXT,
    model           VARCHAR,
    content         TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(conversation_id, "order")
);

-- 検証機能（質問→タグ→情報源, ADR-0048 / IMPL-202608260909）。
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
