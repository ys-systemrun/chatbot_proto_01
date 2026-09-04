# ADR-0074: タグ・タグフォルダへの表示順序（display_order）導入

- ステータス: Accepted
- 日付: 2026-09-03
- 関連: `docs/requirement/202609031501_タグ・タグフォルダ表示順序導入要件定義書.md`、ADR-0005、ADR-0006、ADR-0072、ADR-0073

## コンテキスト

`hiroba_tag`（is-a階層、`parent_tag_id`）・`hiroba_tag_folder`（分類フォルダ階層、ADR-0073の`parent_folder_id`）は、いずれも管理画面（`TagTreePage.tsx`）でツリー表示されるが、兄弟ノード同士の並び順を制御する手段を持たない。現状の`TagRepository.list_tags`/`list_tag_folders`はいずれも`ORDER BY id`（＝作成順）で固定されており、運用担当者が意味のある順序（利用頻度順、関連するタグ同士をまとめる順序等）に並べ替えることができない。タグ・タグフォルダの件数が増えるにつれ、この制約が管理画面の使い勝手を損なっている。

## 決定

**`hiroba_tag`・`hiroba_tag_folder`の両テーブルに、兄弟ノード（同じ`parent_tag_id`／`parent_folder_id`を持つノード集合）内でのローカルな表示順序を表す`display_order`列（`DOUBLE PRECISION`）を追加し、管理画面に「1つ上へ／1つ下へ」ボタンによる並べ替え操作を追加する。**

```sql
ALTER TABLE hiroba_tag
    ADD COLUMN IF NOT EXISTS display_order DOUBLE PRECISION;

ALTER TABLE hiroba_tag_folder
    ADD COLUMN IF NOT EXISTS display_order DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_hiroba_tag_parent_tag_id_display_order
    ON hiroba_tag (parent_tag_id, display_order);

CREATE INDEX IF NOT EXISTS idx_hiroba_tag_folder_parent_folder_id_display_order
    ON hiroba_tag_folder (parent_folder_id, display_order);
```

主要な設計判断は次の4点。

### 1. 対象範囲：タグ（is-a階層）・タグフォルダ（分類階層）の両方

`hiroba_tag`と`hiroba_tag_folder`は別テーブル・別の親子関係だが、いずれも`TagTreePage.tsx`という同一の管理画面上でツリー表示されており、「意味のある順序に並べ替えたい」という運用ニーズは両者に共通する。`display_order`は両テーブルに独立した列として追加し、それぞれ自分自身の親子関係（`parent_tag_id`／`parent_folder_id`）を単位にローカルな順序を持つ。

### 2. 操作UIは「1つ上へ／1つ下へ」ボタンのみとし、ドラッグ&ドロップは対象外とする

ADR-0073の要件定義書ではフォルダ移動UIの方式（ドラッグ&ドロップかプルダウンか）を実装時判断としていたが、本ADRでは並び替え操作を隣接ノードとの入れ替えに限定した「1つ上へ／1つ下へ」ボタン方式のみをスコープとする。任意の位置への挿入（ドラッグ&ドロップ）は行わない。これにより、フロントエンドの実装（座標計算・ドロップ判定を伴わない単純なボタン操作）とバックエンドAPI（後述のとおり「上/下方向への1ステップ移動」のみを受け付ける単純な契約）の両方を最小限に保てる。

### 3. データモデルは間隔採番（gap-based）＋差分UPDATE方式とし、`display_order`はfloat型で持つ

連番（1,2,3...）を密に採番し、1件の移動のたびに影響範囲全体の値を再採番（範囲UPDATE）するのではなく、`display_order`を`DOUBLE PRECISION`として、初期値は十分な間隔（1000.0刻み）を空けて採番する。ノードを1つ上／下へ移動する際は、移動先の前後にあるノードの`display_order`の中間値を計算し、移動対象ノード1件のみを更新する（他の兄弟ノードの値は変更しない）。

- 「1つ上へ」：移動対象ノードの1つ前の兄弟をB、Bのさらに1つ前の兄弟をA（存在しない場合は下限として0）とすると、移動対象ノードの新しい`display_order`は`(A.display_order + B.display_order) / 2`（Aが存在しない場合は`B.display_order / 2`）。
- 「1つ下へ」：移動対象ノードの1つ後ろの兄弟をC、Cのさらに1つ後ろの兄弟をD（存在しない場合はCの値に固定の間隔を加えた値）とすると、移動対象ノードの新しい`display_order`は`(C.display_order + D.display_order) / 2`（Dが存在しない場合は`C.display_order + GAP`）。
- 新規作成時：同じ兄弟集合内の現在の最大`display_order`に固定の間隔（`GAP = 1000.0`）を加えた値を採用する（兄弟が存在しない場合は`GAP`そのものを初期値とする）。末尾に追加される現状の体感（`ORDER BY id`）を踏襲する。
- 親の付け替え（既存の`move_tag`/`move_tag_folder`によるreparent）が行われた場合、位置指定の手段を持たないため、新しい親の兄弟集合の末尾（最大`display_order` + `GAP`）に追加する。

この方式は、更新対象が常に移動ノード1件のみで済み（範囲UPDATEが発生しない）、かつ将来ドラッグ&ドロップによる任意位置への挿入に対応する場合も同じ「2値の中間値を取る」計算をそのまま再利用できる（「1つ上へ」を、任意の2ノード間への挿入の特殊形として実装しておく）という利点がある。

### 4. 一意性制約は設けず、`display_order`が一致した場合は`id`を安定ソートのタイブレークとする

`(parent_id, display_order)`にUNIQUE制約を設けることは行わない。中間値計算によって理論上ごく稀に既存値と一致する可能性を完全には排除できないため、一覧取得時のソートは`ORDER BY parent_id, display_order, id`とし、`display_order`が一致した場合でも表示順序が不定にならないようにする。

## 検討した代替案

- **密な連番＋範囲UPDATE方式**: 1,2,3...の整数を隙間なく振り、1件の移動のたびに影響範囲の全行を再採番する。実装の見通しは立てやすいが、兄弟数が多い場合に1回の移動操作で更新行数が増える。将来ドラッグ&ドロップに拡張する際も同じ考え方を流用できるが、任意位置への挿入のたびに範囲UPDATEが発生する点は変わらない。今回はより更新コストの小さい間隔採番＋差分UPDATE方式を採用した。
- **ドラッグ&ドロップによる任意位置への並べ替えを最初から実装する**: UI体験は優れるが、「別の親配下への移動」と「兄弟内の任意位置への挿入」が同時に起こるUI操作となり、座標計算・ドロップ位置判定の実装コストが増える。今回はまず「1つ上へ／1つ下へ」ボタンによる隣接ノード入れ替えのみをスコープとし、ドラッグ&ドロップは将来の拡張候補として見送った（データモデルは中間値計算方式のため、将来の拡張時にスキーマ変更は不要と見込む）。
- **`(parent_id, display_order)`にUNIQUE制約を設ける**: 整合性は高まるが、中間値計算の結果が既存値と衝突した場合の再試行ロジックが必要になり、実装が複雑化する。今回は一覧取得時に`id`をタイブレークにする方式で十分と判断し、制約は設けないこととした。

## 結果・影響

- `db_hiroba_qa_init`に、`hiroba_tag.display_order`・`hiroba_tag_folder.display_order`列追加、両インデックス追加、既存データへの初期値一括採番（`parent_tag_id`／`parent_folder_id`ごとに現行の`id`順で1000.0刻みの値を付与）のマイグレーションが追加される（詳細は要件定義書`202609031501`参照）。
- `knowledge_mcp`の`TagRepository`に、`reorder_tag(tag_id, direction)`・`reorder_tag_folder(folder_id, direction)`が新設され、`list_tags`/`list_tag_folders`の並び順が`ORDER BY id`から`ORDER BY parent_id, display_order, id`へ変更される。`create_tag`/`create_tag_folder`（CSV一括インポートである`import_tag_batch`（ADR-0053/0061）経由の作成を含む）は、新規作成時に兄弟集合の末尾へ`display_order`を採番するよう改修される。既存の`move_tag`/`move_tag_folder`（ADR-0005/0073）は、reparent後に新しい親の兄弟集合の末尾へ`display_order`を再設定するよう改修される。
- `web_backend`の`tag_controller.py`に、並べ替え操作用エンドポイント（`PATCH /api/tags/{tag_id}/reorder`、`PATCH /api/tag-folders/{folder_id}/reorder`、ボディに`direction: "up" | "down"`）が新設される。
- `front_dev`の`TagTreePage.tsx`に、タグ・タグフォルダそれぞれのツリー表示上で兄弟ノードに対する「1つ上へ／1つ下へ」ボタンが追加される。境界（先頭/末尾）ノードではボタンを無効化する。
- `TagPicker.tsx`のフォルダ別グルーピング表示（`groupTagsByFolder`）内でのタグの並び順をどう扱うかは、本ADRのスコープでは決定しない（フォルダに割り当てられたタグは異なる`parent_tag_id`の兄弟集合をまたぐため、単純に`display_order`だけでは一意な順序を決められない。結果・影響最後尾およびOpen Issues参照）。
- `search_knowledge`・`QARepository.search`・`qa_tag`・ADR-0058/0059のロジックには一切変更を加えない。`display_order`は表示専用の属性であり、検索結果・スコアには影響しない（ADR-0072・ADR-0073の方針を継続）。
- 理論上、同一の2値の間で中間値計算を極端な回数（浮動小数点の実用上の精度限界に達するまで、目安として50回超）繰り返した場合、`display_order`の値が丸め誤差により隣接ノードと区別できなくなる可能性がある。通常の手動操作でこの回数に達することは想定しにくいため、MVPでは対応を見送るが、将来的に問題が顕在化した場合は兄弟集合単位の再採番（メンテナンス操作）を追加する（Open Issues参照）。
