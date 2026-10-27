# agent_invitro/src/main — エントリポイント群

agent_invitro を起動・利用する入口を置きます。AWS 環境で Uvicorn から起動する FastAPI サーバー（`api/`）と、ローカルの IPython で対話実験するための入口（`ipython/`）があり、互いに独立しています。

## 構成

| 名前 | 説明 |
|---|---|
| [`api/`](api/README.md) | 常駐 HTTP サーバー（`/health`・`/ask-pipeline`・`/ask-agentic`・`/release`）。起動パスは `agent_invitro.main.api.server:app`（ADR-0043 / ADR-0090）。 |
| [`ipython/`](ipython/README.md) | IPython から呼ぶ `build()` / `run()`。ReAct エージェントの実験用（ADR-0019）。 |
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
