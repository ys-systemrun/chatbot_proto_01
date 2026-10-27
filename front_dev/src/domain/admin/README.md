# front_dev/src/domain/admin/ — 管理画面の型定義

`/admin/*` の管理画面と `api.ts` が使う、web_backend（Knowledge MCP 経由）の管理 API の入出力型。
検索対象フラグ `is_searchable`（ADR-0092 / ADR-0093）は QA・言い換え・トラブルシューティングの各型に含まれる。

## 構成

| 名前 | 説明 |
|---|---|
| [`qa.ts`](qa.ts) | 広場QA の一覧/詳細・検索条件・作成/更新リクエスト・カテゴリ・CSV インポート結果の型。`feature/qa_admin` で使用。 |
| [`question_altered.ts`](question_altered.ts) | 言い換え質問文（`is_primary=false` の行）の一覧項目・検索条件・作成/更新リクエスト・CSV インポート結果の型（ADR-0064）。親QAの検索対象フラグ `qa_is_searchable` も持つ。`feature/question_altered` で使用。 |
| [`tag.ts`](tag.ts) | タグ（階層 `TagNode`・エイリアス）、タグフォルダ（ADR-0072/0073）、並べ替え（ADR-0074）、エイリアス CRUD（ADR-0080）、CSV インポート結果の型。`feature/tag_admin` 等で使用。 |
| [`troubleshooting.ts`](troubleshooting.ts) | トラブルシューティング記事の一覧/詳細・検索条件・更新リクエスト・出自（source_key）一覧の型（ADR-0079）。新規作成・削除は対象外。`feature/troubleshooting_admin` で使用。 |
| [`verification.ts`](verification.ts) | 検証機能（質問 → タグ → 情報源）の検証質問・実行結果（選定タグ/情報源・レイテンシ・評価）・評価リクエスト・CSV インポート結果の型。`feature/verification` で使用。 |
