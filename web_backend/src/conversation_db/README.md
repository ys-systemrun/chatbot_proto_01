# web_backend/src/conversation_db/ — conversation データベースの会話・評価アクセス

conversation データベース（`CONVERSATION_DB_URL`）の `conversation` / `message` / `release` テーブルを psycopg2 で読み書きするコンテキストマネージャーとデータクラス。会話評価（`/api/evaluate_response`・`/api/evaluated_messages`）と、agent_invitro 中継時のリリース登録（ADR-0099）で使われる。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | `ConversationDB` と各データクラスを再エクスポートする。 |
| [`db.py`](db.py) | `ConversationDB`。会話とメッセージの upsert、リリース（回答を生成した構成）の存在確認・登録、評価済み会話の全件取得を行う。`evaluation_controller` と `agent_controller` から呼ばれる。 |
| [`models.py`](models.py) | `MessageRecord`（保存するメッセージ。評価・リリース ID・ask_mode・評価コメントを含む）、`ReleaseData`（リリース情報）、`EvaluatedMessageData` / `EvaluatedConversationData`（一覧取得結果）の dataclass 定義。 |
