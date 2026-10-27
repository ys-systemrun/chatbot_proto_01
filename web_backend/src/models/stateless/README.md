# web_backend/src/models/stateless/ — stateless 会話のメッセージモデル

クライアントが履歴を毎回送る stateless 会話で使うメッセージモデル。`__init__.py` は無く、`src.models.stateless.message` として直接 import される。

## 構成

| 名前 | 説明 |
|---|---|
| [`message.py`](message.py) | `Message`。順序（order）・role（user / assistant / system）・content を持つ。`chat_controller` と `llm/summarize_llm*.py` が使用。 |
