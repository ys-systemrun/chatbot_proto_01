# web_backend/src/session/ — 会話状態のセッションストア

`ConversationState`（`models/stateful`）をセッション ID に紐づけて保存・取得・削除するストア。共通インターフェースに対しメモリ・ファイル・Redis の 3 実装を持つ。現在の呼び出し元は旧 stateful アプリ（`main/main.py`、`InMemorySessionStore` を使用）のみ。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | インターフェースと 3 実装を再エクスポートする。 |
| [`base.py`](base.py) | `get` / `save` / `delete` を持つインターフェース `SessionStore`（Protocol）。 |
| [`file_store.py`](file_store.py) | `FileSessionStore`。セッションごとに `<store_dir>/<session_id>.json` へ JSON で永続化する（単一サーバー向け）。 |
| [`in_memory.py`](in_memory.py) | `InMemorySessionStore`。プロセス内の辞書に保持する（再起動で消える。開発・テスト向け）。 |
| [`redis_store.py`](redis_store.py) | `RedisSessionStore`。Redis に TTL（既定 30 分）付きで保存する（分散環境向け。`redis` パッケージは pyproject の依存に含まれないため別途インストールが必要）。 |
