# web_backend/src/models/stateful/ — サーバー側で保持する会話状態のモデル

会話履歴とスロット（キー・値）をサーバー側で保持する方式のモデル。CLI チャット（`main/chat.py`）・旧 stateful アプリ（`main/main.py`）と、`src/session` のセッションストアが使う。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | `Message` / `Slot` / `ConversationState` を再エクスポートする。 |
| [`conversation_state.py`](conversation_state.py) | `ConversationState`。メッセージ履歴・検索コンテキスト・スロットを持ち、LLM API 用 dict への変換や、セッションストア保存用の `to_dict` / `from_dict` を提供する。 |
| [`message.py`](message.py) | `Message`。role（user / assistant / system）と content を持ち、dict 変換できる。 |
| [`slot.py`](slot.py) | `Slot`。会話中に保持するキー・値の組。 |
