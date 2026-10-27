# front_dev/src/feature/common/ — 管理画面の共有部品

複数の管理画面から使う UI 部品。画面そのもの（ルート）は持たない。

## 構成

| 名前 | 説明 |
|---|---|
| [`QaPicker.tsx`](QaPicker.tsx) | QA 検索ピッカー。キーワード（タイトル・質問文の部分一致）で `GET /api/qa` を約 300ms デバウンスで呼び、候補から QA を選ぶ（ADR-0064）。言い換え質問文の新規作成フォームと一覧の QA 絞り込みで使用。 |
| [`SearchableToggle.tsx`](SearchableToggle.tsx) | 検索対象フラグ `is_searchable` の共通 UI（ADR-0092 / ADR-0093）。一覧行の即時保存トグル `SearchableToggle`、3 値（すべて / 検索可のみ / 検索不可のみ）の絞り込みセレクト `SearchableFilterSelect` と、URL クエリ ⇄ API 引数の変換関数。QA・言い換え・トラブルシューティングの各一覧で使用。 |
