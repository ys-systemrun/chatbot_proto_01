# agent_invitro/src/main/ipython — IPython 用エントリポイント

ローカルで `docker compose exec agent_invitro ipython` から ReAct エージェントを対話的に試すための入口です（ADR-0019）。HTTP サーバー（`main/api/`）とは独立しています。使い方は [agent_invitro/README.md](../../../README.md) の「使い方」を参照してください。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`main.py`](main.py) | `build()`（設定読み込み → LLM・MCP クライアント・ツール取得 → `build_agent`）と `run(agent, query)`（1クエリ実行し、ツール呼び出し・結果・最終回答を出力）。いずれも async で、IPython の top-level await で呼ぶ。 |
