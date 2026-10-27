# front_dev/src/feature/qa_admin/ — 広場QA の管理画面

管理サブナビ「広場QA」から開く QA の一覧・新規作成・編集画面（`/admin` の既定遷移先）。画面遷移図の 2.2・3.3・3.4 節を参照。
一覧の検索条件・ページ位置は URL クエリに同期し、フォームへは `back` パラメータで引き継ぐ（ADR-0068）。

## 構成

| 名前 | 説明 |
|---|---|
| [`QaListPage.tsx`](QaListPage.tsx) | QA 一覧（`/admin/qa`）。キーワード・カテゴリ・タグ（`TagPicker`）・検索対象での絞り込み、ページング、行ごとの検索対象トグル（即時保存）・編集リンク・削除、CSV 一括インポートを持つ。言い換え数も列表示する。 |
| [`QaFormPage.tsx`](QaFormPage.tsx) | QA の新規作成（`/admin/qa/new`, `mode="create"`）／編集（`/admin/qa/:id`, `mode="edit"`）フォーム。タイトル・質問文・回答文・カテゴリ・タグ・検索対象フラグを保存し、編集時は削除もできる。`back` はホワイトリスト検証して一覧へ戻る。 |
| [`deleteConfirm.ts`](deleteConfirm.ts) | QA 削除時の確認ダイアログ文言 `QA_DELETE_CONFIRM`（ADR-0067）。一覧・編集の両画面で共用する。 |
