# front_dev/ — 管理・デバッグ用フロントエンド（React + Vite SPA）

チャットボットの動作確認用チャット画面・評価済みメッセージ一覧・QA/タグ等の管理画面をまとめた React 18 + TypeScript の SPA。
ローカルでは `docker-compose.yml` の `frontend` サービス（Vite dev server, ポート 5173）として起動し、`/api` 等を `web_backend` へプロキシする（ADR-0015）。
AWS では `web_backend/Dockerfile.admin_ui` が本フォルダを本番ビルドして `web_backend` に同梱・静的配信する（ADR-0042）。
画面とルートの対応は [`docs/screen_transition/画面遷移図.md`](../docs/screen_transition/画面遷移図.md) を参照。

## 構成

| 名前 | 説明 |
|---|---|
| [`.storybook/`](.storybook/README.md) | Storybook 8（`@storybook/react-vite`）の設定。`npm run storybook` でポート 6006 に起動する。 |
| [`src/`](src/README.md) | アプリ本体のソース（ルート定義・API クライアント・型定義・画面コンポーネント・CSS）。 |
| [`Dockerfile`](Dockerfile) | ローカル開発用イメージ（node:20-alpine）。依存をインストールし `npm run dev` で Vite dev server を起動する。5173（Vite）/ 6006（Storybook）を公開。`docker-compose.yml`・`docker-compose.storybook.yml` から使われる。 |
| [`index.html`](index.html) | SPA のエントリ HTML。`#app` 要素と `/src/main.tsx` の読み込みのみを持つ（タイトル「Chatbot Debug UI」）。 |
| [`package.json`](package.json) | npm パッケージ定義。スクリプト `dev` / `build`（`tsc && vite build`）/ `preview` / `storybook` / `build-storybook` と、React・react-router-dom・Storybook・Vite 等の依存を宣言する。 |
| [`package-lock.json`](package-lock.json) | 依存バージョンのロックファイル（`Dockerfile.admin_ui` の `npm ci` でも使用）。 |
| [`tsconfig.json`](tsconfig.json) | TypeScript 設定（`src` を対象、`noEmit`・`strict`・`jsx: react-jsx`）。ローカルの dev / build / Storybook で使う。 |
| [`tsconfig.build.json`](tsconfig.build.json) | AWS 本番ビルド専用の tsconfig。`tsconfig.json` を継承し、`*.stories.ts(x)` を型チェック対象から除外する（ADR-0042）。 |
| [`vite.config.ts`](vite.config.ts) | Vite 設定。React プラグインと dev server（0.0.0.0:5173）のプロキシ設定（`/api`・`/ask`・`/session` → `http://web_backend:8000`）を持つ。 |

※ `node_modules/`（依存パッケージ）や `dist/`（ビルド成果物）は .gitignore 対象のため表には載せていない。
