# ADR-0064: 言い換え質問文（question_altered）管理機能の実装方式（Knowledge MCP経由、主質問文行を対象外とする設計）

- ステータス: Accepted
- 日付: 2026-08-27
- 関連: `docs/requirement/202608271750_言い換え質問文（question_altered）管理機能要件定義書.md`, ADR-0013, ADR-0014, ADR-0015, ADR-0046, ADR-0047, ADR-0053, ADR-0061

## コンテキスト

ADR-0014により、`qa_original`の登録・編集（`create_qa`/`update_qa`）は、`question_text`に対応する`question_altered`行を1件（`is_primary=true`）自動生成・自動更新する。同ADRは同時に、「既存データ投入時にLLMで生成された複数の`question_altered`（パラフレーズ）行は、本ツールの対象外とする」「`question_altered`の複数パラフレーズをUIから管理したいという要望が出た場合は、別途要件定義・ADRが必要になる」と明記しており（要件定義書202608060826 Open Issue #3）、本ADRはこのOpen Issueに対応するものである。

現状、`question_altered`テーブルには、初期データ投入時にLLMで生成された`is_primary=false`のパラフレーズ行が多数存在するが、これらを一覧・検索・新規追加・編集する手段がない。発注者より、`question_altered`単体を対象とした一覧ページ・CSV一括インポートページ・新規作成ページ・編集ページを追加したいという要望が示された。加えて、既存の全データエクスポート機能（ADR-0047）とは別に、`question_altered`テーブル単体を「そのまま再インポートできる形式」でCSVエクスポートする機能も要望された。

`question_altered`は`qa_original.uuid`を参照する`qa_id`列を持つが外部キー制約はなく（`db_hiroba_qa_init/migrations/0002_question_altered_table.py`）、embedding計算にはKnowledge MCPが保持する`embed_fn`（LM Studio / Bedrock embedding呼び出し、ADR-0014）が必要である。また、`is_primary=true`行は`create_qa`/`update_qa`が「常に1件のみ存在する主質問文行であり、`qa_original.question_text`と対応する」という前提で管理しており、この前提を新機能が壊すと、チャット検索（`search_knowledge`）や既存QA編集フォームの動作に影響し得る。

## 決定

**`knowledge_mcp`に、`question_altered`の「言い換え行」（`is_primary=false`）のみを対象とする新規MCPツール群（`list_question_altered` / `get_question_altered` / `create_question_altered` / `update_question_altered` / `delete_question_altered` / `import_question_altered_batch` / `export_question_altered`）を追加する。`is_primary=true`の主質問文行は、引き続き`create_qa`/`update_qa`のみが生成・更新し、新機能では作成・変更しない。`web_backend`はこれらのツールをREST API化するBFFとして振る舞い（ADR-0013の既存方針を維持）、`chatbot`データベースへの直接読み書きは行わない。**

1. **対象範囲の分離**: `create_question_altered`は常に`is_primary=false`で行を作成する（`is_primary`をリクエストパラメータとして受け付けない）。`update_question_altered`は対象行が`is_primary=true`の場合は`QuestionAlteredError`を送出して拒否する（主質問文行の編集は既存のQA編集フォームに委ねる）。これにより、`create_qa`/`update_qa`が前提とする「`qa_id`ごとに`is_primary=true`行は常に1件」という不変条件を、新機能側から破らないようにする。
2. **`create_question_altered`**: `qa_id`（必須、既存`qa_original.uuid`であることを検証）・`text`（必須）を受け取り、既存の`embed_fn`で embedding を計算して`question_altered`行（`is_primary=false`）を1件追加する。
3. **`update_question_altered`**: `id`（必須）・`text`（必須）を受け取り、対象行の存在と`is_primary=false`であることを検証したうえで、`text`とembeddingを再計算する。`qa_id`の付け替えは提供しない（対象外、要件定義書4.2節）。
4. **`delete_question_altered`**: `id`（必須）を受け取り、対象行の存在と`is_primary=false`であることを検証したうえで削除する。対象が`is_primary=true`の場合はエラーを返す（主質問文行は本機能を含め既存システム全体に削除手段がないため、削除自体を提供しない）。`question_altered.id`を参照する外部キーは他に存在しないため、削除に伴う追加の整合性チェックは不要である。
5. **`list_question_altered`**: `qa_id`（任意、絞り込み）・`keyword`（任意、`text`部分一致）・`limit`/`offset`によるページングで、`is_primary=false`行を一覧する。表示用に`qa_original.title`を結合して返す。
6. **CSV一括インポート（`import_question_altered_batch`）**: 既存の`import_qa_batch`（ADR-0053）・`import_tag_batch`（ADR-0061）と同じ設計方針（行単位のエラー許容、既存ロジックのループ適用）を踏襲する。列は`id`・`qa_id`・`text`・`is_primary`とし、`id`が空欄の行は新規作成（`is_primary`列の値は無視し常に`false`で作成）、`id`が既存行と一致する行は更新（対象が`is_primary=true`の場合はエラー行として報告する）とする。行削除はこのバッチツールでは扱わない（後述の代替案検討を参照）。
7. **CSVエクスポート（`export_question_altered`）**: `is_primary=false`行のみを対象に、`id`・`qa_id`・`text`・`is_primary`の4列（`embedding`列は含めない）でCSVを生成する。この列構成は、既存の全データエクスポート（ADR-0047）における`question_altered.csv`の列定義（`id`, `qa_id`, `text`, `is_primary`。`embedding`を除く）と同一とし、エクスポート結果を`import_question_altered_batch`へそのまま再投入できる形式にする。
8. **既存の全データエクスポート（ADR-0046/0047）との関係**: 本ツールは、ADR-0046が新設した読み取り専用ロール（`CHATBOT_EXPORT_DB_URL`）を経由せず、Knowledge MCP経由（ADR-0013の原則）で実装する。既存の全データエクスポート機能（8テーブルのZIP、`is_primary=true`行を含む全行が対象）は変更せず、独立した別機能として併存させる。

## 検討した代替案

- **既存の全データエクスポート機構（`web_backend/src/export/tables.py`、ADR-0046の読み取り専用ロール）を拡張し、`question_altered`単体のCSVダウンロードエンドポイントを追加する**: 列定義（`id`/`qa_id`/`text`/`is_primary`、`embedding`除外）が既に`tables.py`に存在し、実装コストは最小で済む利点がある。しかし、本機能が新設する「言い換え行のみを対象とする」というビジネスルール（`is_primary=false`のみエクスポート）を、書き込み側（Knowledge MCP）と読み取り側（`web_backend`の直接SQL）の2箇所に重複実装することになり、将来どちらかだけが変更されて対象範囲がずれるリスクを負う（ADR-0013がQA・タグの二重実装を避けた理由と同じ懸念）。CSVインポート・エクスポート・一覧表示が同じ「言い換え行」という業務概念を扱う以上、同一コンポーネント（Knowledge MCP）に業務ロジックを一本化する方を優先し、不採用とした。全データエクスポート（バックアップ・移行目的、`is_primary`を問わず全件対象）は、本機能とは目的・対象範囲が異なる別機能として、変更せず併存させる。
- **`create_question_altered`/`update_question_altered`に`is_primary`パラメータを設け、trueを指定した場合は同一`qa_id`の他行を自動的に`false`へ更新することで一意性を保証する（主質問文行への昇格を許可する）**: `is_primary=true`行の管理をこの新機能に一本化できる利点があるが、`is_primary=true`行は`qa_original.question_text`と対応するという既存の前提（ADR-0014）があり、新機能経由で`text`のみを更新して`is_primary=true`に昇格させると、`qa_original.question_text`との同期が取れなくなる（`search_knowledge`のスコアリングやQA編集フォームの表示に影響し得る）。この同期処理を新機能側にも実装すると、`update_qa`のロジックとの二重実装になるため不採用とした。主質問文行の管理は引き続き`create_qa`/`update_qa`に一本化する。
- **CSV一括インポートの重複判定を、検証質問一括インポート（ADR-0054）と同様に「常に新規追加のみ」とする**: 実装は単純だが、既存の言い換え行のテキストを一括で修正したい（誤字修正等）という主要ユースケースに対応できず、CSVエクスポート→編集→再インポートという往復運用（本機能の主目的の一つ）が成立しない。QA一括インポート（ADR-0053）と同様の`id`列によるupsert方式を採用した。
- **CSVインポートに`delete`フラグ列（またはそれに類する指定）を設け、CSV経由の一括削除にも対応する**: 一括削除の運用ニーズが本ADRの時点では明確でなく、対応範囲を広げると誤操作時の一括削除リスク（レビューなしに大量の行が消える）を新たに抱える。まずは一覧・編集ページからの個別削除（確認ダイアログを伴う単体操作）で運用を開始し、一括削除の必要性が明らかになった時点で別途要件化する方が安全と判断し、本ADRではCSVを介した削除は対象外とした。

## 結果・影響

- `knowledge_mcp`に新規ツール7件（`list_question_altered`/`get_question_altered`/`create_question_altered`/`update_question_altered`/`delete_question_altered`/`import_question_altered_batch`/`export_question_altered`）とその実装（新規`QuestionAlteredRepository`または`QaManagementRepository`の拡張、実装フェーズで確定）が追加される。既存の`create_qa`/`update_qa`/`import_qa_batch`の実装・シグネチャには変更を加えない。
- `web_backend`に新規コントローラ（`question_altered_controller.py`、仮称）とAPIエンドポイント（`/api/question_altered/*`、削除・CSVインポート・エクスポートを含む）が追加される。既存の`/api/qa/*`・全データエクスポート（`/api/export`）には変更を加えない。
- `front_dev`に新規ページ群（一覧・新規作成・編集、削除操作・CSVインポート/エクスポートUIを含む）とQA検索ピッカーコンポーネントが追加され、管理画面ナビ（`AdminLayout`）に新規メニュー項目が追加される（ADR-0015の`/admin`サブツリー方針を踏襲）。
- `is_primary=true`行（主質問文行）の新規作成・編集・削除は、本機能の対象外のまま維持される。`delete_question_altered`はこれらの行を削除できず、主質問文行は既存システム全体で削除手段を持たない状態が続く。将来、主質問文行自体をこの新機能に統合したいという要望が出た場合は、`qa_original.question_text`との同期方法・削除可否を含めて別途ADRが必要になる。
- CSVインポート・エクスポートの列構成（`id`/`qa_id`/`text`/`is_primary`）を全データエクスポート（ADR-0047）と揃えたことで、利用者が全データエクスポートのZIP内`question_altered.csv`を本機能のCSVインポートへ流用できる可能性があるが、その場合`is_primary=true`行を含むため、該当行はインポート時にエラーとして拒否される（想定内の挙動として要件定義書に明記する）。
- ファイルサイズ・件数上限、CSVの区切り文字・文字コード等の詳細は、要件定義書のOpen Issueとして引き継ぐ。
