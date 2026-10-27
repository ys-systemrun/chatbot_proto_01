# front_dev/src/ — SPA のソース本体

`main.tsx` から `routes.tsx` の Router をマウントし、チャット（`/`）・評価（`/evaluated_messages`）・管理（`/admin/*`）の 3 画面グループを描画する（ADR-0015 / ADR-0042）。
型定義は `domain/`、画面は `feature/`、web_backend への HTTP 呼び出しは `api.ts` に集約している。
画面とルートの対応は [`docs/screen_transition/画面遷移図.md`](../../docs/screen_transition/画面遷移図.md) を参照。

## 構成

| 名前 | 説明 |
|---|---|
| [`components/`](components/README.md) | 旧 statefull 版チャット（`App.tsx`）用の UI 部品と stories。現在のルートからは使われていない。 |
| [`domain/`](domain/README.md) | API のリクエスト/レスポンスや画面で扱うデータの型定義（＋回答生成方式の定数など小さなロジック）。 |
| [`feature/`](feature/README.md) | 画面（ページコンポーネント）と画面固有の部品。機能ごとにサブフォルダを分ける。 |
| [`App.tsx`](App.tsx) | 旧 statefull 版チャット画面（`POST /ask`・`DELETE /session/:id` を使うセッション型）。`routes.tsx` からは参照されておらず、現在は未使用（`/` は `feature/stateless/StateContainer` が担当）。 |
| [`api.ts`](api.ts) | web_backend の API クライアント。チャット（`/api/ask-pipeline`・`/api/ask-agentic`）、評価（`/api/evaluate_response`・`/api/evaluated_messages`）、QA・言い換え・タグ・タグフォルダ・トラブルシューティング・検証の CRUD／CSV インポート、エクスポートのダウンロード等を `fetch` で呼ぶ関数群。 |
| [`main.tsx`](main.tsx) | エントリポイント。`style.css` を読み込み、`#app` に `routes.tsx` の `AppRoutes` を `StrictMode` でマウントするだけ。 |
| [`routes.tsx`](routes.tsx) | ルート定義を集約する唯一のファイル。グローバルナビ（チャット / 管理 / 評価）、管理サブナビ（`AdminLayout`）、`/admin` 配下の入れ子ルートと `body.page-*` クラスの付け替えを定義する。 |
| [`style.css`](style.css) | 全画面共通のスタイルシート（チャット、評価一覧の列幅リサイズ、管理画面のフォーム・タグ階層・検索対象トグル等）。Storybook の `preview.ts` からも読み込まれる。 |
