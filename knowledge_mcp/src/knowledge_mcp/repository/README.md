# knowledge_mcp/src/knowledge_mcp/repository — リポジトリ（SQL 層）

ナレッジ DB への SQL をまとめた層です。`search_knowledge` 用の検索リポジトリ（`Repository` 抽象を実装し `SearchService` に登録される）と、管理 UI 向けの管理リポジトリ（CRUD・CSV 一括取込/出力）に分かれます。いずれも内部状態をキャッシュせず、呼び出しごとに DB を参照します（ADR-0006）。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`base.py`](base.py) | 検索リポジトリの抽象基底 `Repository`（`search(query, tags, category, top_k)`）。新しい検索ソースはこれを実装して `SearchService` に登録する。 |
| [`scoring.py`](scoring.py) | 検索スコアの共通ヘルパー。埋め込み距離からのスコア変換 `distance_to_score()`（`1 / (1 + distance)`）とタグ構成類似度の `jaccard()`（ADR-0058 / 0059 / 0078）。 |
| [`csv_flags.py`](csv_flags.py) | CSV 一括取込の真偽値列（`is_searchable`）を解釈する `parse_optional_bool()`（ADR-0094）。QA と言い換え質問文の取込で共用する。 |
| [`qa_repository.py`](qa_repository.py) | `QARepository`。`hiroba_question_altered` のベクトル近傍検索で QA を探し、祖先タグ展開後のタグ類似度と重み付き合成したスコアで `Document` を返す（ADR-0058 / 0059）。 |
| [`troubleshooting_repository.py`](troubleshooting_repository.py) | `TroubleshootingRepository`。`troubleshooting_article` の記事単位の埋め込みで検索し、QA と同じスコアリングで `Document` を返す（ADR-0076 / 0078）。 |
| [`qa_management_repository.py`](qa_management_repository.py) | `QaManagementRepository`。QA（`hiroba_qa_original` / `hiroba_question_altered` / `hiroba_qa_tag`）の一覧・詳細・登録・更新・削除・CSV 一括取込とカテゴリ一覧。質問文の埋め込みも計算する（ADR-0014 / 0053 / 0067）。 |
| [`question_altered_repository.py`](question_altered_repository.py) | `QuestionAlteredRepository`。言い換え質問文（`is_primary=false` 行のみ）の一覧・詳細・登録・更新・削除・CSV 取込/出力（ADR-0064）。主質問文行には書き込まない。 |
| [`tag_repository.py`](tag_repository.py) | `TagRepository` と `TagError`。`tag` / `tag_alias` / `tag_folder` 等の CRUD、階層移動（循環防止）、表示順の並べ替え、同義語管理、タグフォルダ管理、CSV 一括取込/出力（ADR-0006 / 0061 / 0065 / 0072〜0074 / 0080）。 |
| [`troubleshooting_management_repository.py`](troubleshooting_management_repository.py) | `TroubleshootingManagementRepository`。トラブルシューティング記事の一覧・詳細・更新・タグ付けと出自（`source_key`）一覧。埋め込み元のフィールドが変わったら埋め込みを再計算する（ADR-0079）。 |
