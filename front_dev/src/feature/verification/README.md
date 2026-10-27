# front_dev/src/feature/verification/ — 検証（質問 → タグ → 情報源）画面

管理サブナビ「検証」から開く検証機能の画面群。登録した検証質問に対してタグ選定と情報源検索を実行し、結果を記録・評価する。
画面遷移図の 2.5・3.10〜3.12 節を参照。

## 構成

| 名前 | 説明 |
|---|---|
| [`VerificationListPage.tsx`](VerificationListPage.tsx) | 検証質問一覧（`/admin/verification`）。キーワード（質問文・メモ）検索、最終実行の新規タグ・情報源・評価・状態の表示、行ごとの実行・削除、新規作成と詳細へのリンク、CSV 一括インポートを持つ。 |
| [`VerificationDetailPage.tsx`](VerificationDetailPage.tsx) | 検証詳細（`/admin/verification/:id`）。質問内容と実行履歴（選定タグ・情報源・スコア・レイテンシ）を表示し、再実行と各実行への評価（適切/不適切＋コメント）保存、編集画面へのリンクを持つ。 |
| [`VerificationFormPage.tsx`](VerificationFormPage.tsx) | 検証質問の新規作成（`/admin/verification/new`）／編集（`/admin/verification/:id/edit`）フォーム。質問文・メモと既存タグ（タグツリーを平坦化したチェックボックス）を保存する。 |
