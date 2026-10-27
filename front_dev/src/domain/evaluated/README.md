# front_dev/src/domain/evaluated/ — 評価済みメッセージの型定義

評価済みメッセージ一覧画面（`/evaluated_messages`, [`feature/evaluated_messages`](../../feature/evaluated_messages/README.md)）が `GET /api/evaluated_messages` で受け取るデータの型。

## 構成

| 名前 | 説明 |
|---|---|
| [`index.ts`](index.ts) | 会話（`EvaluatedConversation`）とメッセージ（`EvaluatedMessage`：役割・評価・プロンプト・モデル等）、回答を生成した構成 `Release`（git commit・プロンプトハッシュ・モデル ID 等, ADR-0099）の型。 |
