# front_dev/src/feature/stateless/ — チャット画面

グローバルナビ「チャット」のデフォルト画面（`/`）。会話履歴と要約をクライアント側で保持して毎回送る stateless 方式で、
回答生成方式（パイプライン / エージェント）をヘッダーのトグルで切り替える（ADR-0089）。画面遷移図の 3.1 節を参照。

## 構成

| 名前 | 説明 |
|---|---|
| [`messages/`](messages/README.md) | メッセージ一覧と吹き出し（👍/👎 評価・評価理由の入力付き）。 |
| [`StateContainer.tsx`](StateContainer.tsx) | 画面の状態管理（メッセージ・要約・会話 ID・回答方式）。送信時に `askStateless`（`/api/ask-pipeline` / `/api/ask-agentic`）、評価時に `evaluateResponse`（`/api/evaluate_response`）を呼ぶ。`routes.tsx` の `/` に直接割り当てられている。 |
| [`LayoutContainer.tsx`](LayoutContainer.tsx) | 表示レイアウト。`Header`・`MessageList`・`InputBar` を並べ、`StateContainer` から受けた状態とハンドラを渡す。 |
| [`Header.tsx`](Header.tsx) | タイトル「Chatbot Debug UI」と回答生成方式のトグル（パイプライン方式 / エージェント方式）。応答待ち中は無効化する。 |
| [`Header.stories.tsx`](Header.stories.tsx) | `Header` のストーリー（パイプライン / エージェント / 無効化）。 |
| [`InputBar.tsx`](InputBar.tsx) | 質問入力欄と送信ボタン（Ctrl/Cmd+Enter でも送信）、回答に誤りを含む可能性がある旨の注意書き。 |
| [`InputBar.stories.tsx`](InputBar.stories.tsx) | `InputBar` のストーリー（通常 / 無効化）。 |
