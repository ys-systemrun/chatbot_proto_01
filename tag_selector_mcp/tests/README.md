# tag_selector_mcp/tests — Tag Selector MCP の単体テスト

pytest の単体テストです。インメモリの Fake DB・モック LLM・boto3 のモックを使い、実 DB・LLM なしで動きます。各ファイルは `../src` を `sys.path` に追加して `tag_selector_mcp` を import します。`tag_selector_mcp/` で `pytest` を実行します。

## 構成

| 名前 | 説明 |
|---|---|
| [`test_bedrock_llm_client.py`](test_bedrock_llm_client.py) | `BedrockLLMClient` の Converse 呼び出しと、`create_llm_client()` の provider 分岐を検証する。 |
| [`test_inference_engine.py`](test_inference_engine.py) | `InferenceEngine` の `confidence_threshold` 未満の除外、`max_tags` 件への絞り込み、score 降順、JSON パース失敗時のフォールバックを検証する。 |
| [`test_retrieval_engine.py`](test_retrieval_engine.py) | `RetrievalEngine` の確定タグ（同義語一致）と候補（全件）の返し方を検証する。 |
| [`test_tag_metadata_repository.py`](test_tag_metadata_repository.py) | `TagMetadataRepository` のロード・リロード・参照系を検証する。 |
| [`test_tools.py`](test_tools.py) | FastMCP が使える場合に、`select_tags`・`list_taxonomy`・`reload_taxonomy` の入出力とエラー変換を検証する。 |
