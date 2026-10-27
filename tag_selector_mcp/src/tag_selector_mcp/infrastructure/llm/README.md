# tag_selector_mcp/src/tag_selector_mcp/infrastructure/llm — LLM クライアント

`InferenceEngine` が使う LLM クライアントです。`complete(prompt) -> str` という同じインターフェースで、ローカルの LM Studio と AWS の Bedrock を切り替えます（ADR-0012 / ADR-0031）。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | `create_llm_client()`。`LLM_PROVIDER` が `lmstudio` なら `LMStudioLLMClient`、`bedrock` なら `BedrockLLMClient` を作る（必要な設定が無ければ `ValueError`）。`mcp/server.py` から呼ばれる。 |
| [`base.py`](base.py) | 抽象基底 `LLMClient`（`complete(prompt)` が応答テキストを返す）。 |
| [`lmstudio.py`](lmstudio.py) | `LMStudioLLMClient`。LM Studio の OpenAI 互換 Chat Completions API を requests で呼ぶ（タイムアウト 120 秒）。 |
| [`bedrock.py`](bedrock.py) | `BedrockLLMClient`。Bedrock の Converse API を boto3 で呼ぶ。認証は boto3 の既定チェーン（ECS タスクロール等）に任せ、タイムアウトと再試行は環境変数で調整できる（ADR-0102）。 |
