# front_dev/src/domain/statefull/ — 旧 statefull 版チャットの型定義

セッション ID をサーバ側で持つ旧 statefull 版チャット（`POST /ask`）用の型。
参照元は [`../../App.tsx`](../../App.tsx)・[`../../components/`](../../components/README.md)・`api.ts` の `ask()` で、いずれも現在の `routes.tsx` からは使われていない。

## 構成

| 名前 | 説明 |
|---|---|
| [`types.ts`](types.ts) | `POST /ask` のリクエスト（`session_id`・`text`）／レスポンス（`session_id`・`answer`）と、画面上の 1 メッセージ `MessageItem`（user / assistant / error）の型。 |
