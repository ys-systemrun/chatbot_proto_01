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
