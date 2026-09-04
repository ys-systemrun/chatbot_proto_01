-- 統合マイグレーション 0007（ADR-0073 / REQ-202609030857）
-- タグフォルダ（hiroba_tag_folder）をフラットな1階層から、フォルダ同士が親子関係を
-- 持てるツリー構造へ拡張する。
--   1. 自己参照の parent_folder_id 列を追加する（NULL=ルートフォルダ）。
--   2. parent_folder_id にインデックスを張る。
--   3. フォルダ名の一意性制約（ADR-0072 の name UNIQUE）を撤廃する。
--      フォルダの識別は id のみで行い、name は表示用ラベルとして重複を許容する（ADR-0073 決定1）。
-- parent_folder_id はタグの is-a 階層（hiroba_tag.parent_tag_id）とも search_knowledge の
-- 検索ロジックとも完全に独立した、分類表示専用メタデータの見出し構造である（ADR-0072 の方針を継続）。
-- 既存フォルダの parent_folder_id は全件 NULL（ルート直下）として扱う。
-- 冪等（IF NOT EXISTS / DROP CONSTRAINT IF EXISTS）。

ALTER TABLE hiroba_tag_folder
    ADD COLUMN IF NOT EXISTS parent_folder_id INTEGER REFERENCES hiroba_tag_folder(id);

CREATE INDEX IF NOT EXISTS idx_hiroba_tag_folder_parent_folder_id
    ON hiroba_tag_folder (parent_folder_id);

ALTER TABLE hiroba_tag_folder DROP CONSTRAINT IF EXISTS hiroba_tag_folder_name_key;
