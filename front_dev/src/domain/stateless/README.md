# front_dev/src/domain/stateless/ — 現行チャット画面の型定義

チャット画面（`/`, [`feature/stateless`](../../feature/stateless/README.md)）が使う型。会話履歴と要約をクライアント側で保持し、毎回リクエストに載せて送る stateless 方式。
回答生成方式（パイプライン / エージェント）の切り替えもここで定義する（ADR-0088 / ADR-0089）。

## 構成

| 名前 | 説明 |
|---|---|
| [`ask_mode.ts`](ask_mode.ts) | 回答生成方式 `AskMode`（`pipeline` / `agentic`）と、方式ごとの API パス（`/api/ask-pipeline`・`/api/ask-agentic`）・表示ラベル・既定値、localStorage への選択保存/読込関数。 |
| [`message.ts`](message.ts) | 会話の 1 メッセージ `Message`（順序・役割・本文、assistant のプロンプト・モデル・評価・評価理由・リリース ID・回答方式, ADR-0099）。 |
| [`request.ts`](request.ts) | 回答生成 API のリクエスト `Request`（会話 ID・質問文・未要約メッセージ・要約）。 |
| [`response.ts`](response.ts) | 回答生成 API のレスポンス `Response`（会話 ID・メッセージ一覧・要約）。 |
| [`summary.ts`](summary.ts) | 会話要約 `Summary`（ID・要約本文・要約済みの順序番号 `summarized_upto`）。 |
