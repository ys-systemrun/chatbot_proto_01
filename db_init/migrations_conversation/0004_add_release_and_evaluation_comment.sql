-- ADR-0099 段階① conversation マイグレーション 0004
-- 回答を生成した構成（リリース）と方式、評価の理由を記録する。
--   message.release_id / ask_mode : 回答を生成したリリースと方式（"pipeline" | "agentic"）。
--   message.evaluation_comment / evaluated_at : 評価の理由（任意）と、評価・理由を最後に変更した日時。
--   release : リリースの全要素。agent_invitro の GET /release の内容を admin_ui が登録する。
-- message.release_id には外部キーを張らない（回答時の登録が失敗しても会話・評価の保存を妨げないため）。
-- 冪等（IF NOT EXISTS）。

ALTER TABLE message
    ADD COLUMN IF NOT EXISTS release_id VARCHAR;

ALTER TABLE message
    ADD COLUMN IF NOT EXISTS ask_mode VARCHAR;

ALTER TABLE message
    ADD COLUMN IF NOT EXISTS evaluation_comment TEXT;

ALTER TABLE message
    ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX IF NOT EXISTS idx_message_release_id ON message (release_id);

CREATE TABLE IF NOT EXISTS release (
    release_id          VARCHAR PRIMARY KEY,
    git_commit          VARCHAR,
    git_dirty           BOOLEAN,
    prompt_hash         VARCHAR,
    chat_model_id       VARCHAR,
    embedding_model_id  VARCHAR,
    params              TEXT,  -- 回答に効く設定値の JSON 文字列
    first_seen_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
