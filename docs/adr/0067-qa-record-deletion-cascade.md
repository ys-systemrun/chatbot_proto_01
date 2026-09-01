# ADR-0067: QAレコード削除機能の実装方式（カスケード削除・一覧編集両ページからの単一削除）

- ステータス: Accepted
- 日付: 2026-08-31
- 関連: `docs/requirement/202608311540_QAレコード削除機能要件定義書.md`, ADR-0013, ADR-0014, ADR-0015, ADR-0041, ADR-0048, ADR-0053, ADR-0064

## コンテキスト

ADR-0014により`knowledge_mcp`に追加された`create_qa`/`update_qa`/`list_qa`/`get_qa`/`list_categories`は、QA（`qa_original`）の登録・編集・参照のみを提供し、削除機能を含まない。言い換え質問文（`question_altered`）管理機能（ADR-0064）は、`delete_question_altered`が主質問文行（`is_primary=true`）を削除できない仕様であることを明記したうえで、Open Issue #7として「QA自体の削除機能（`delete_qa`）が別途必要かどうかも含め、要望が出た場合に別途要件化する」と記録していた。発注者より、QA一覧ページ（`QaListPage`）およびQA編集ページ（`QaFormPage`）からQAレコードを削除できるようにしたいという要望が示され、本ADRはこの要望とOpen Issue #7の両方に対応するものである。

`qa_original`（`uuid` PK）は、`qa_tag`（`qa_id` → `qa_original.uuid`への外部キー制約あり、`ON DELETE`句なし）から参照されているため、単純な`DELETE FROM qa_original`は、当該QAにタグが1件でも紐づいていれば外部キー違反で失敗する。一方`question_altered`（`qa_id`列を持つが外部キー制約なし）は、`qa_original`を削除しても自動的には削除されず、`qa_id`が存在しない孤立行として残る（`search_knowledge`等の既存クエリが`question_altered`→`qa_original`のLEFT JOINを用いているため、孤立行の残存は将来的な不具合要因になり得る）。

既存の削除機能には2通りの先例がある。`delete_tag`は「`qa_tag`・子タグから参照されていれば削除を拒否する」方式であり、`delete_question_altered`は「参照する外部キーが存在しないため追加の整合性チェックは不要」という前提のシンプルな削除である。QAは通常タグが付与されており、また`question_altered`（主質問文行）を必ず1件以上持つため、いずれの先例もそのままは適用できない。また、検証実行履歴（`verification_run_source`、conversationデータベース）・会話ログは、`chatbot`データベースのQAをクロスデータベースで参照しているが外部キー制約はなく（ADR-0048）、削除に伴うカスケードは技術的に不可能である。

## 決定

**`knowledge_mcp`に新規MCPツール`delete_qa`を追加し、対象QAに紐づく`qa_tag`行・`question_altered`行（`is_primary`を問わず全件）を同一トランザクション内でカスケード削除したうえで`qa_original`行を削除する。`web_backend`は既存パターンを踏襲した薄いBFF（`DELETE /api/qa/{qa_id}`）としてこれを公開し、`front_dev`のQA一覧ページ・QA編集ページの双方に、確認ダイアログを伴う単一削除の操作を追加する。**

1. **`delete_qa`（knowledge_mcp）**: `qa_id`（必須）を受け取り、`QaManagementRepository.delete_qa`を呼び出す。まず対象QAの存在を検証し（既存の`get_qa`と同様の存在チェック）、存在しない場合は`QaError`を送出する。存在する場合、同一トランザクション内で `DELETE FROM qa_tag WHERE qa_id = %s` → `DELETE FROM question_altered WHERE qa_id = %s` → `DELETE FROM qa_original WHERE uuid = %s` の順に削除する。`qa_tag`を先に削除するのは、外部キー制約上`qa_original`より先に削除する必要があるためであり、`question_altered`はどちらのタイミングでも削除可能だが、同一トランザクション内でまとめて処理することで孤立行の発生を防ぐ。
2. **カスケード方式の採用（`delete_tag`の拒否方式は不採用）**: QAは運用上ほとんどの行にタグが付与される想定であり、`delete_tag`と同様の「参照があれば拒否」方式を採用すると、事前に手動でタグを全解除しない限り削除できず、実用上ほぼ使用できない機能になる。そのため、対象QAに紐づく`qa_tag`・`question_altered`を自動的にカスケード削除する方式を採用する。
3. **主質問文行の削除**: `question_altered`のカスケード削除は`is_primary`の値を問わず全件を対象とする。これにより、`delete_question_altered`が提供できない「主質問文行の削除」が、QA自体の削除を経由することで初めて可能になる（ADR-0064 Open Issue #7への対応）。ただし、QAを残したまま主質問文行だけを削除する手段は、本ADR後も引き続き提供しない。
4. **クロスデータベース参照への対応**: 検証実行履歴（`verification_run_source`）・会話ログへのカスケード削除は行わない。`chatbot`データベースと conversationデータベース間に外部キー制約がなく（ADR-0048）、技術的にトランザクションを跨いだ整合したカスケードを実装できないためである。代わりに、削除確認ダイアログ（`front_dev`側）で「これらの履歴・ログへの参照は削除後も残存し得る」旨を利用者に明示することで、既知の制約として運用上受容する。
5. **`web_backend`の変更**: 既存の`delete_tag`/`delete_item`（`question_altered_controller.py`）と同一パターンで`qa_controller.delete_qa(qa_id)`を追加し、`delete_qa`ツールを呼び出したうえで`log_admin_operation("delete", "qa", qa_id, {})`を実行する。`app.py`に`@app.delete("/api/qa/{qa_id}", status_code=204)`ルートを追加する。既存のグローバル例外ハンドラ（`KnowledgeMcpError` → `409`）をそのまま利用し、コントローラ側での個別の例外処理は追加しない。
6. **`front_dev`の変更**: `QaListPage`の各行に削除操作を追加し、`QaFormPage`の編集モードのみに削除ボタンを追加する（既存の`QuestionAlteredFormPage`の配置・スタイル・`window.confirm`パターンを踏襲する）。いずれも確認ダイアログには、タグ・言い換え質問文が同時に削除されること、検証実行履歴・会話ログの参照は残存し得ること、操作が取り消せないこと、の3点を含める。削除は1件単位のみとし、一覧ページでの複数選択一括削除・CSVインポート経由の削除フラグは、本ADRの対象外とする。

## 検討した代替案

- **`delete_tag`と同様の「参照があれば削除拒否」方式**: `qa_tag`に1件でも行があれば`delete_qa`をエラーにし、事前に手動でタグを解除させる方式。実装は単純だが、QAは通常タグ付けされる運用が前提であり、拒否方式では発注者が求める「一覧・編集ページから削除できる」という要求を実質的に満たせない（毎回タグ解除の手間が発生する）ため不採用とした。
- **論理削除（`is_deleted`フラグ等のソフトデリート）の導入**: 削除の取り消しや誤操作からの復旧が可能になる利点がある。しかし、本システムの既存の削除機能（`delete_tag`/`delete_question_altered`/`delete_verification_question`）はすべてハードデリートであり、スキーマ上も論理削除フラグは一切存在しない。QAのみ異なる削除方式を導入すると、一覧表示・検索（`search_knowledge`・`list_qa`）側でも`is_deleted`の除外条件を新たに考慮する必要が生じ、影響範囲が本ADRのスコープを大きく超える。発注者からもソフトデリートの要望はなく、既存の設計方針との一貫性を優先して不採用とした。
- **検証実行履歴・会話ログ側のカスケード削除・整合性維持を本機能に含める**: `verification_run_source`・会話ログの該当レコードを検出し、削除または「参照先QA削除済み」のマークを付ける案。技術的には、`chatbot`データベースとconversationデータベースを跨いだ処理が必要になり、ADR-0048が定めた「クロスデータベースの外部キー制約を持たない」という既存方針を前提から見直すことになる。影響範囲・実装コストが大きく、かつ発注者からの要望も確認ダイアログでの告知で足りるとのことだったため、本ADRでは対象外とし、確認ダイアログでの利用者への告知にとどめた。
- **CSVインポートに削除フラグ列を追加し、一括削除にも対応する**: ADR-0064が検討し不採用とした代替案と同じ懸念（一括削除の運用ニーズが明確でない段階で対応範囲を広げると、レビューなしに大量のQAが削除されるリスクを新たに抱える）が当てはまるため、本ADRでも同様に不採用とした。まずは一覧・編集ページからの個別削除（確認ダイアログを伴う単体操作）で運用を開始し、必要性が明らかになった時点で別途要件化する。

## 結果・影響

- `knowledge_mcp`に新規ツール`delete_qa`と、`QaManagementRepository`への`delete_qa`メソッドが追加される。既存の`create_qa`/`update_qa`/`list_qa`/`get_qa`/`list_categories`/`import_qa_batch`の実装・シグネチャには変更を加えない。
- `web_backend`に`qa_controller.delete_qa`と`DELETE /api/qa/{qa_id}`ルートが追加される。既存の`/api/qa`系エンドポイント（一覧・詳細・作成・編集・CSVインポート）には変更を加えない。
- `front_dev`の`QaListPage.tsx`・`QaFormPage.tsx`が変更され、`api.ts`に`deleteQa(id)`が追加される。
- QA削除に伴い、そのQAに紐づく`qa_tag`・`question_altered`（主質問文行・言い換え行の両方）が自動的に削除される。これにより、ADR-0064のOpen Issue #7（主質問文行の削除手段がない）は、「QA自体を削除すれば主質問文行も削除される」という形で解消されるが、QAを残したまま主質問文行のみを削除する手段は引き続き提供されない。
- 検証実行履歴（`verification_run_source`）・会話ログに残るQAへの参照は、削除後も自動的には整理されない。これは本ADRが新たに生む問題ではなく、ADR-0048が既に許容しているクロスデータベース非外部キー方針の延長であり、削除確認ダイアログでの告知によって運用上受容する。
- 一覧ページでの複数選択一括削除、CSVインポート経由の一括削除、論理削除・復元機能はいずれも未実装のまま残る。将来これらの要望が出た場合は、別途要件定義・ADRが必要になる。
