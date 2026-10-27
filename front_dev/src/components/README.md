# front_dev/src/components/ — 旧 statefull 版チャットの UI 部品

セッション ID を持つ旧 statefull 版チャット画面（[`../App.tsx`](../App.tsx)）の部品群。型は `domain/statefull/types.ts` を使う。
現在の `/` チャット画面は [`feature/stateless/`](../feature/stateless/README.md) の同名部品を使っており、本フォルダの部品は `routes.tsx` からは到達しない（Storybook には `Components/*` として表示される）。

## 構成

| 名前 | 説明 |
|---|---|
| [`Header.tsx`](Header.tsx) | タイトル「Chatbot Debug UI」とセッション ID 表示、「セッションリセット」ボタンを持つヘッダー。 |
| [`Header.stories.tsx`](Header.stories.tsx) | `Header` のストーリー（セッション未開始 / セッションあり / 無効化）。 |
| [`InputBar.tsx`](InputBar.tsx) | 質問入力欄（textarea）と送信ボタン。Ctrl/Cmd+Enter でも送信し、送信中は無効化する。 |
| [`InputBar.stories.tsx`](InputBar.stories.tsx) | `InputBar` のストーリー（通常 / 無効化）。 |
| [`MessageBubble.tsx`](MessageBubble.tsx) | 1 メッセージの吹き出し（あなた / アシスタント / エラー）。アシスタントは API レスポンス JSON を折りたたみ表示できる。 |
| [`MessageBubble.stories.tsx`](MessageBubble.stories.tsx) | `MessageBubble` のストーリー（ユーザー / アシスタント / 生レスポンス付き / エラー）。 |
| [`MessageList.tsx`](MessageList.tsx) | メッセージ一覧。`MessageBubble` を並べ、応答待ち中はローディング表示を出し、更新時に末尾へ自動スクロールする。 |
| [`MessageList.stories.tsx`](MessageList.stories.tsx) | `MessageList` のストーリー（空 / 会話 / エラー含む / ローディング）。 |
