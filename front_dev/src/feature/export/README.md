# front_dev/src/feature/export/ — 全データエクスポート画面

管理サブナビ「エクスポート」から開く全データエクスポート画面（`/admin/export`）。画面遷移図の 3.13 節を参照。

## 構成

| 名前 | 説明 |
|---|---|
| [`ExportPage.tsx`](ExportPage.tsx) | SQL / CSV をラジオボタンで選び「エクスポート」で ZIP をダウンロードする（`api.ts` の `downloadExport`）。処理中はボタンを無効化し、成功・失敗をページ内に表示する。 |
