# front_dev/src/feature/stateless/messages/ — チャット画面のメッセージ表示

チャット画面（`/`）のメッセージ一覧と吹き出し。アシスタントの回答に 👍/👎 評価と評価理由を付けられる（ADR-0099 §4）。

## 構成

| 名前 | 説明 |
|---|---|
| [`MessageList.tsx`](MessageList.tsx) | メッセージを順に `MessageBubble` で表示し、応答待ち中はローディング表示、更新時は末尾へ自動スクロールする。評価操作を `order` 付きで親へ伝える。 |
| [`MessageList.stories.tsx`](MessageList.stories.tsx) | `MessageList` のストーリー（空 / 会話 / エラー含む / ローディング）。 |
| [`MessageBubble.tsx`](MessageBubble.tsx) | 1 メッセージの吹き出し（あなた / アシスタント / エラー）。アシスタントには 👍/👎 ボタン（再押下で取り消し）と評価理由の入力・保存欄（👎 時は自動で開く）を表示する。 |
| [`MessageBubble.stories.tsx`](MessageBubble.stories.tsx) | `MessageBubble` のストーリー（ユーザー / アシスタント / エラー）。 |
