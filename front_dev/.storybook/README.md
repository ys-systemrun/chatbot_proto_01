# front_dev/.storybook/ — Storybook 設定

`front_dev/src` 配下の `*.stories.ts(x)` を Storybook 8（`@storybook/react-vite`）で表示するための設定。
`npm run storybook`（ポート 6006）、またはリポジトリルートの `docker-compose.storybook.yml` で起動する。

## 構成

| 名前 | 説明 |
|---|---|
| [`main.ts`](main.ts) | Storybook 本体設定。stories の探索対象（`../src/**/*.stories.@(ts\|tsx)`）、アドオン（essentials / interactions）、フレームワーク（react-vite）を指定する。 |
| [`preview.ts`](preview.ts) | 全ストーリー共通のプレビュー設定。`src/style.css` を読み込み、controls の color / date マッチャーを設定する。 |
