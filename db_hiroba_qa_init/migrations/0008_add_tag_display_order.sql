-- 統合マイグレーション 0008（ADR-0074 / REQ-202609031501）
-- tag（is-a 階層、parent_tag_id）・tag_folder（分類フォルダ階層、parent_folder_id）の
-- 兄弟ノード（同じ親を持つノード集合）内でのローカルな表示順序 display_order（DOUBLE PRECISION）を
-- 導入する。管理画面（TagTreePage.tsx）の「1つ上へ／1つ下へ」ボタンによる並べ替えの基盤。
--   1. 両テーブルに display_order 列を追加する（間隔採番＝gap-based、float型, ADR-0074 決定3）。
--   2. 既存データへ、現行の一覧順（id 順）と体感が変わらないよう、parent ごとに id 順で
--      1000.0 刻みの初期値を一括採番する（display_order IS NULL の行のみ＝再実行安全）。
--   3. 採番後、両列を NOT NULL 化する（以降の INSERT は必ず値を明示設定する, 要件6.1）。
--   4. (parent, display_order) の複合インデックスを追加する。
-- display_order は分類・並べ替えの表示専用属性であり、search_knowledge の検索ロジック
-- （ADR-0058 祖先展開・ADR-0059 タグ構成類似度）・スコアには一切関与しない（ADR-0072/0073/0074 継続）。
-- 冪等（IF NOT EXISTS / WHERE display_order IS NULL）。
-- ADR-0077: 共有タグマスタを中立名称 tag / tag_folder へ改名。

ALTER TABLE tag
    ADD COLUMN IF NOT EXISTS display_order DOUBLE PRECISION;

ALTER TABLE tag_folder
    ADD COLUMN IF NOT EXISTS display_order DOUBLE PRECISION;

-- 既存データへの初期値一括採番（parent_tag_id ごとに、現行の id 順を 1000.0 刻みへ変換）。
WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY parent_tag_id ORDER BY id) AS rn
    FROM tag
    WHERE display_order IS NULL
)
UPDATE tag AS t
SET display_order = ranked.rn * 1000.0
FROM ranked
WHERE t.id = ranked.id;

WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY parent_folder_id ORDER BY id) AS rn
    FROM tag_folder
    WHERE display_order IS NULL
)
UPDATE tag_folder AS t
SET display_order = ranked.rn * 1000.0
FROM ranked
WHERE t.id = ranked.id;

ALTER TABLE tag ALTER COLUMN display_order SET NOT NULL;
ALTER TABLE tag_folder ALTER COLUMN display_order SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tag_parent_tag_id_display_order
    ON tag (parent_tag_id, display_order);

CREATE INDEX IF NOT EXISTS idx_tag_folder_parent_folder_id_display_order
    ON tag_folder (parent_folder_id, display_order);
