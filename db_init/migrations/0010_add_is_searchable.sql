-- REQ-202609160930 / 統合マイグレーション 0010（ADR-0092）
-- 情報源レコードの検索対象フラグ is_searchable を3テーブルへ追加する。
-- 既定値 true のため、適用直後の検索挙動は適用前と完全に同一である。
-- 冪等（ADD COLUMN IF NOT EXISTS）。ダウングレードステップは用意しない（0004 / 0005 と同方針）。
-- 索引は追加しない（値の大半が true で選択率が低く、候補取得はベクトル距離順の全走査のため）。

ALTER TABLE hiroba_qa_original
    ADD COLUMN IF NOT EXISTS is_searchable BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE hiroba_question_altered
    ADD COLUMN IF NOT EXISTS is_searchable BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE troubleshooting_article
    ADD COLUMN IF NOT EXISTS is_searchable BOOLEAN NOT NULL DEFAULT true;
