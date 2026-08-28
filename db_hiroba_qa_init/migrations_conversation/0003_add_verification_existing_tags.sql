-- IMPL-202608261510 / ADR-0060 conversation マイグレーション 0003
-- 検証機能への既存タグ入力パラメータ追加（既存タグ・新規タグの記録方針, ADR-0060）。
-- existing_tags（verification_question）・existing_tags_snapshot（verification_run）は
-- タグ名のJSON配列文字列を TEXT に保存する（verification_run_tag.path と同じ方式）。
-- 冪等（IF NOT EXISTS）。

ALTER TABLE verification_question
    ADD COLUMN IF NOT EXISTS existing_tags TEXT;

ALTER TABLE verification_run
    ADD COLUMN IF NOT EXISTS existing_tags_snapshot TEXT;
