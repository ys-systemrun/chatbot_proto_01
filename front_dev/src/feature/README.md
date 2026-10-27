# front_dev/src/feature/ — 画面（ページコンポーネント）と画面固有の部品

`routes.tsx` から描画される各画面を、機能ごとのサブフォルダに分けて置く。画面間の遷移とスクリーンショットは
[`docs/screen_transition/画面遷移図.md`](../../../docs/screen_transition/画面遷移図.md) を参照。

## 構成

| 名前 | 説明 |
|---|---|
| [`common/`](common/README.md) | 複数の管理画面で共有する部品（QA 検索ピッカー、検索対象フラグのトグル/絞り込み）。 |
| [`evaluated_messages/`](evaluated_messages/README.md) | 評価済みメッセージ一覧画面（`/evaluated_messages`、グローバルナビ「評価」）。 |
| [`export/`](export/README.md) | 全データエクスポート画面（`/admin/export`）。 |
| [`qa_admin/`](qa_admin/README.md) | 広場QA の一覧・新規作成・編集画面（`/admin/qa`・`/admin/qa/new`・`/admin/qa/:id`）。 |
| [`question_altered/`](question_altered/README.md) | 言い換え質問文の一覧・新規作成・編集画面（`/admin/hiroba_question_altered` 配下）。 |
| [`stateless/`](stateless/README.md) | チャット画面（`/`、グローバルナビ「チャット」）。 |
| [`tag_admin/`](tag_admin/README.md) | タグ階層管理画面（`/admin/tags`）と、他画面でも使うタグピッカー・タグ検索ロジック。 |
| [`troubleshooting_admin/`](troubleshooting_admin/README.md) | トラブルシューティング記事の一覧・編集画面（`/admin/troubleshooting` 配下）。 |
| [`verification/`](verification/README.md) | 検証（質問 → タグ → 情報源）の一覧・詳細・新規作成/編集画面（`/admin/verification` 配下）。 |
