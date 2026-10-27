# front_dev/src/domain/ — 型定義（API の入出力・画面データ）

web_backend とやり取りするリクエスト/レスポンスや、画面で扱うデータの TypeScript 型をまとめるフォルダ。
UI を持たず、`api.ts` と `feature/` の各画面から import される。用途（画面グループ）ごとにサブフォルダを分けている。

## 構成

| 名前 | 説明 |
|---|---|
| [`admin/`](admin/README.md) | 管理画面（`/admin/*`）用の型。QA・言い換え質問文・タグ・トラブルシューティング記事・検証。 |
| [`evaluated/`](evaluated/README.md) | 評価済みメッセージ一覧（`/evaluated_messages`）用の型。 |
| [`statefull/`](statefull/README.md) | 旧 statefull 版チャット（`POST /ask`）用の型。現在のルートでは未使用の `App.tsx`・`components/` と `api.ts` の `ask()` が参照する。 |
| [`stateless/`](stateless/README.md) | 現行チャット画面（`/`）用の型と、回答生成方式（パイプライン / エージェント）の定数・保存処理。 |
