# terraform/deploy — デプロイオーケストレータ（コンテナ内 Python）

`terraform/*.bat` の実体となるデプロイ処理（ADR-0040。旧 `terraform/scripts/*.ps1` を置き換え）。
Python + terraform（バージョン固定）+ docker CLI + dvc を同梱したイメージ `chatbot-deploy:latest` を作り、リポジトリを `/work` にマウントしてコンテナ内で `deploy <コマンド>` を実行する。ホストに必要なのは Docker Desktop だけ。
設定は `terraform/.env` から読み込む（使い方の全体は [`terraform/README.md`](../README.md)）。

## 構成

| 名前 | 説明 |
|---|---|
| [`src/`](src/README.md) | `deploy` コマンドの Python パッケージ（CLI・各コマンド本体・AWS / terraform / docker / dvc 呼び出し） |
| [`tests/`](tests/README.md) | pytest によるテスト（AWS・terraform には触れずスタブで検証） |
| [`run.bat`](run.bat) | 共通ランナー。各 `terraform\*.bat` から `call` され、毎回 `docker build`（レイヤキャッシュで高速）→ `docker run`（リポジトリを `/work` に、ホストの Docker ソケットを共有、プロバイダキャッシュを名前付きボリュームに）で `deploy` に引数を渡す |
| [`Dockerfile`](Dockerfile) | デプロイ用イメージの定義。python:3.11-slim に terraform・docker CLI（client のみ, DooD）・dvc[s3] を入れ、git の safe.directory / autocrlf を設定し、`src` を pip install して `deploy` を ENTRYPOINT にする |
| [`pyproject.toml`](pyproject.toml) | パッケージ `chatbot-deploy` の定義（依存は boto3 のみ、コンソールスクリプト `deploy = src.__main__:main`） |
| [`.dockerignore`](.dockerignore) | イメージビルド時に除外するもの（`__pycache__`・`.pytest_cache`・`tests/`・`.env` 等） |

> Git 管理外: `.pytest_cache/`（pytest のキャッシュ）。
