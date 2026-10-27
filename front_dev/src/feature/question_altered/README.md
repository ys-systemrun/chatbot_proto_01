# front_dev/src/feature/question_altered/ — 言い換え質問文の管理画面

管理サブナビ「広場言い換え」から開く、QA の言い換え質問文（`is_primary=false` の行）の一覧・新規作成・編集画面（ADR-0064）。
画面遷移図の 2.3・3.5・3.6 節を参照。一覧の検索条件は URL クエリに同期し、`back` パラメータでフォームへ引き継ぐ（ADR-0068）。

## 構成

| 名前 | 説明 |
|---|---|
| [`QuestionAlteredListPage.tsx`](QuestionAlteredListPage.tsx) | 言い換え質問文一覧（`/admin/hiroba_question_altered`）。QA（`QaPicker`）・キーワード・検索対象での絞り込み、ページング、行ごとの検索対象トグル・編集リンク・削除、CSV インポート/エクスポートを持つ。親QAが検索対象外の行はバッジで示す。 |
| [`QuestionAlteredFormPage.tsx`](QuestionAlteredFormPage.tsx) | 言い換えの新規作成（`/admin/hiroba_question_altered/new`）／編集（`/:id`）フォーム。新規は `QaPicker` で対象QAを選んで本文を入力、編集は本文と検索対象フラグのみ変更可（対象QAは読み取り専用で QA 編集画面へのリンク付き）。削除もできる。 |
