# ADR-0014: QAデータの登録・編集機能をKnowledge MCPのツールとして追加する

- ステータス: Accepted
- 日付: 2026-08-06
- 関連: ADR-0003, ADR-0006, ADR-0013, `docs/requirement/202608060826.md`

## コンテキスト

ADR-0006では、タグマスタ（`tag`テーブル）の登録・編集をKnowledge MCPのMCPツールとして提供する方針を決定した。一方、QAデータ本体（`qa_original` / `question_altered` / `qa_tag`）の登録・編集を担うコンポーネントは、これまでどこにも存在しなかった（既存の `QARepository` は検索専用の読み取りしか行わない）。

`docs/requirement/202608060826.md` の要件（QA登録・編集フォーム）を実現するには、QAデータの作成・更新に加えて、`question_text` に対応する `question_altered` 行のテキストとembeddingベクトルを計算・保存する処理が必要になる。この処理は、既存 `QARepository` が検索時に利用している `embed_fn`（LM Studio embedding APIの呼び出し）と同じ仕組みを必要とする。また、ADR-0013の決定（管理系書き込みはKnowledge MCP経由に統一する）を実現するには、このQA登録・編集処理自体をKnowledge MCP側に実装する必要がある。

## 決定

Knowledge MCP サーバに、QA管理用の新規MCPツール `list_qa` / `get_qa` / `create_qa` / `update_qa`、および補助的な参照専用ツール `list_categories` を追加する。

- `create_qa` / `update_qa` は、既存 `QARepository` が利用する `embed_fn` を再利用し、`question_text` の登録・変更時に `question_altered` 行（1件）のテキストとembeddingを計算・保存する。
- タグ紐付け（`qa_tag`）の変更は、`create_qa` / `update_qa` の `tag_ids` パラメータで、指定された集合への置き換えとして行う。
- 既存データ投入時にLLMで生成された複数の `question_altered`（パラフレーズ）行は、本ツールの対象外とする（`create_qa` は常に1件のみ生成し、`update_qa` はその1件のみを再計算する）。

## 検討した代替案

- **`web_backend` 側に新規Repository（既存 `src/db.py` の拡張）を実装し、`qa_original` 等へ直接書き込む方式**: ADR-0013と同じ理由（業務ロジックの重複）に加え、embedding計算のためのLM Studio接続情報（`LMSTUDIO_EMBEDDING_URL` / `MODEL_EMBEDDING`）へのアクセスがKnowledge MCPと`web_backend`の両方に必要になり、設定の重複・将来の設定不一致のリスクが生じるため見送った。
- **QA管理専用の別MCPサーバを新設する方式**: Knowledge MCPは既に `QARepository`／embedding連携（`search_knowledge`）を持ち、QAデータと最も強く責務が重なるコンポーネントである。別サーバに分割すると、`qa_original`の読み取り（検索）と書き込み（登録編集）が別コンポーネントに分かれ、スキーマ変更時の影響範囲がむしろ広がるため、過剰な分割と判断し見送った。

## 結果・影響

- Knowledge MCPの責務が「検索実行」からさらに拡大する（ADR-0006でのタグ管理機能追加と同様の傾向）。将来、責務分離の観点でQA管理・タグ管理を専用の別コンポーネントへ切り出す可能性は、要件定義書のOpen Issueとして残す。
- `create_qa` / `update_qa` の実行時間は、embedding計算（LM Studio APIへのHTTP呼び出し）を含むため、`search_knowledge` 等の読み取り専用ツールより長くなることが見込まれる。詳細設計時にタイムアウト・エラーハンドリング方針を確定する。
- 既存データ投入バッチ（`data/exportjson_withguid.json` からの一括投入）とは独立した経路であり、本ツールの追加によって既存投入処理の挙動は変更されない。
- `question_altered` の複数パラフレーズをUIから管理したいという要望が出た場合は、別途要件定義・ADRが必要になる（要件定義書 Open Issue #3）。
