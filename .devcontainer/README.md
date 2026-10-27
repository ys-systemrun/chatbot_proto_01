# .devcontainer/ — VS Code Dev Container の設定

VS Code の Dev Containers でリポジトリを開いたときの開発用コンテナ（Ubuntu 24.04 + Python 3.11 / Node 20 / Go 1.23）の定義です。
アプリ本体の実行環境は `docker-compose.yml` 側で、ここはエディタ用の環境です。

## 構成

| 名前 | 説明 |
|---|---|
| [`devcontainer.json`](devcontainer.json) | コンテナ定義。Python・Node・Go の features、VS Code 拡張機能（Python / Ruff / Go / ESLint / Prettier 等）とフォーマッタ設定、`front_dev/node_modules` の名前付きボリューム、`postCreateCommand` を指定する |
| [`Dockerfile`](Dockerfile) | ベースイメージ（`mcr.microsoft.com/devcontainers/base:ubuntu-24.04`）の指定のみ |
| [`postCreate.sh`](postCreate.sh) | コンテナ作成後に実行する初期化スクリプト。`app/` の `pip install -e .`、`front_dev` の `npm install`、`data/` の `go mod tidy` を行う（`app/` は現在のリポジトリには無い旧構成の名残） |
| [`devcontainer-lock.json`](devcontainer-lock.json) | features の解決済みバージョンとダイジェスト（Dev Containers が自動生成するロックファイル） |
