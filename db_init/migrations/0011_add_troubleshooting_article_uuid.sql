-- 統合マイグレーション 0011（ADR-0106）
-- トラブルシューティング記事に、DB の採番に依存しない識別子 uuid を追加する。
-- 値はシード（db_init の troubleshooting_import）が入れる。CSV 由来は CSV の guid 列、HTML 由来は
-- (source_key, title) から UUID v5 で決める。既存行は次回シードで埋める（バックフィル）ため NULL を許す。
-- 冪等（ADD COLUMN IF NOT EXISTS / CREATE UNIQUE INDEX IF NOT EXISTS）。ダウングレードステップは用意しない。

ALTER TABLE troubleshooting_article
    ADD COLUMN IF NOT EXISTS uuid TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_troubleshooting_article_uuid
    ON troubleshooting_article (uuid);
