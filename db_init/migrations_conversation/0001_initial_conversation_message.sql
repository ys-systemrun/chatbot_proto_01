-- IMPL-202608261022 / ADR-0051 conversation マイグレーション 0001
-- 現行 db_conversation/init.sql の内容（conversation / message テーブル）をそのまま移植する。
-- chatbot データベースとは独立した conversation データベースへ、yoyo（migrations_conversation/）で適用する。
-- 冪等（CREATE TABLE IF NOT EXISTS）。既存ボリュームは README のベースライン化（yoyo mark）で
-- 「適用済み」として登録すること（5.3 節）。

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
