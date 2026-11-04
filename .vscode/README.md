# .vscode/ — VS Code のワークスペース設定

このリポジトリを VS Code で開いたときの設定です。`extensions.json`（推奨拡張機能）と この README は git で共有し、`settings.json` は個人の環境に依存する値を含むため git の対象外にする（`.gitignore`）。

## 構成

| 名前 | 説明 |
|---|---|
| [`settings.json`](settings.json) | VS Code の DVC 拡張機能が使う `dvc.exe` のパス（Windows のインストール先） |
| [`extensions.json`](extensions.json) | 推奨拡張機能。DVC（`iterative.dvc`）と、DVC 管理の CSV を表で見る・編集する Rainbow CSV（`mechatroner.rainbow-csv`）・Edit csv（`janisdd.vscode-edit-csv`） |
