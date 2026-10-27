# front_dev/src/feature/evaluated_messages/ — 評価済みメッセージ一覧画面

チャット画面で 👍/👎 評価された会話を一覧する画面（`/evaluated_messages`、グローバルナビ「評価」）。
画面遷移図の 3.2 節を参照。列幅リサイズは ADR-0087、理由・方式・リリース列とリリース絞り込みは ADR-0099。

## 構成

| 名前 | 説明 |
|---|---|
| [`EvaluatedMessagesPage.tsx`](EvaluatedMessagesPage.tsx) | `GET /api/evaluated_messages` の会話ごとにカードとメッセージ表（#・役割・評価・理由・方式・リリース・モデル・本文・LLM 入力・登録日時）を表示する。リリースでの絞り込み、列見出しのドラッグによる列幅変更（全テーブル同時反映・localStorage 保存）と「列幅をリセット」を持つ。`routes.tsx` の `EvaluatedLayout` から描画される。 |
