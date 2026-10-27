# knowledge_mcp/tests — Knowledge MCP の単体テスト

pytest の単体テストです。SQL とパラメータを記録して固定行を返す Fake DB や、boto3 / requests のモックを使い、実 DB・埋め込み API なしで動きます。各ファイルは `../src` を `sys.path` に追加して `knowledge_mcp` を import します。`knowledge_mcp/` で `pytest` を実行します。

## 構成

| 名前 | 説明 |
|---|---|
| [`test_embed_fn.py`](test_embed_fn.py) | `mcp/server.py` の `_make_embed_fn()` の provider 分岐（LM Studio / Bedrock の Titan・Cohere）を検証する。 |
| [`test_qa_management_repository.py`](test_qa_management_repository.py) | `QaManagementRepository` の登録・更新・詳細・一覧（必須項目検証、存在しないカテゴリ/タグの検出、質問文変更時の埋め込み再計算、ページング等）を検証する。 |
| [`test_qa_repository.py`](test_qa_repository.py) | `QARepository` のスコア変換、Jaccard、category 条件、`Document` への変換、タグ構成類似度との合成スコアを検証する。 |
| [`test_question_altered_repository.py`](test_question_altered_repository.py) | `QuestionAlteredRepository` が書き込みで `is_primary=false` を守り、主質問文行・不存在・`qa_id` 付け替えを拒否することなどを検証する。 |
| [`test_search_service.py`](test_search_service.py) | `SearchService` の複数リポジトリ集約・score 降順ソート・`top_k` 切り詰めを検証する。 |
| [`test_tools.py`](test_tools.py) | `TagRepository` のタグ操作（作成・名称変更・移動・削除・循環防止・説明・同義語・フォルダ等）と、FastMCP が使える場合の `search_knowledge` の `min_score` フィルタ・`ToolError` 変換を検証する。 |
| [`test_troubleshooting_repository.py`](test_troubleshooting_repository.py) | `TroubleshootingRepository`（検索）と `TroubleshootingManagementRepository`（管理）を検証する。 |
