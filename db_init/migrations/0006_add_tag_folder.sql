-- 統合マイグレーション 0006（ADR-0072）
-- タグフォルダ（parent_tag_id による is-a 階層とは独立した分類表示専用メタデータ）を新設する。
-- tag_folder マスタテーブルと tag.folder_id 外部キーを追加する。
-- folder_id は管理画面・選択UIのグルーピング表示専用であり、search_knowledge の検索ロジック
-- （ADR-0058 祖先展開・ADR-0059 タグ構成類似度）には一切使用しない。
-- 冪等（IF NOT EXISTS）。
-- ADR-0077: 共有タグマスタを中立名称 tag / tag_folder へ改名。

CREATE TABLE IF NOT EXISTS tag_folder (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);

ALTER TABLE tag
    ADD COLUMN IF NOT EXISTS folder_id INTEGER REFERENCES tag_folder(id);

CREATE INDEX IF NOT EXISTS idx_tag_folder_id ON tag (folder_id);
