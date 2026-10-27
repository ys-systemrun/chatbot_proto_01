# front_dev/src/feature/troubleshooting_admin/ — トラブルシューティング記事の管理画面

管理サブナビ「トラブルシューティング」から開く、トラブルシューティング記事の一覧・編集画面（ADR-0079）。新規作成・削除は対象外。
画面遷移図の 2.4・3.7・3.8 節を参照。一覧からフォームへは `back` パラメータで検索条件・ページ位置を引き継ぐ（ADR-0068）。

## 構成

| 名前 | 説明 |
|---|---|
| [`TroubleshootingListPage.tsx`](TroubleshootingListPage.tsx) | 記事一覧（`/admin/troubleshooting`）。キーワード（タイトル・現象・案内内容）・出自（source_key）・タグ（`TagPicker`）・検索対象での絞り込み、ページング、行ごとの検索対象トグル（即時保存）と編集リンクを持つ。 |
| [`TroubleshootingFormPage.tsx`](TroubleshootingFormPage.tsx) | 記事編集フォーム（`/admin/troubleshooting/:id`, `mode="edit"`）。タイトル・現象・エラーコード・案内内容・原因等のテキスト項目、タグ、検索対象フラグを保存する。出自・元更新日時・元 HTML（`body_html`）は読み取り専用で表示する。 |
