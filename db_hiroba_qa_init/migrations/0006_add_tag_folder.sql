-- 統合マイグレーション 0006（ADR-0072）
-- タグフォルダ（parent_tag_id による is-a 階層とは独立した分類表示専用メタデータ）を新設する。
-- hiroba_tag_folder マスタテーブルと hiroba_tag.folder_id 外部キーを追加する。
-- folder_id は管理画面・選択UIのグルーピング表示専用であり、search_knowledge の検索ロジック
-- （ADR-0058 祖先展開・ADR-0059 タグ構成類似度）には一切使用しない。
-- 冪等（IF NOT EXISTS）。

CREATE TABLE IF NOT EXISTS hiroba_tag_folder (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);

ALTER TABLE hiroba_tag
    ADD COLUMN IF NOT EXISTS folder_id INTEGER REFERENCES hiroba_tag_folder(id);

CREATE INDEX IF NOT EXISTS idx_hiroba_tag_folder_id ON hiroba_tag (folder_id);
