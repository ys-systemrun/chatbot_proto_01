# agent_invitro/src/llm_tasks — 差し替え可能な LLM 機能

LLM や外部 AI サービスを呼び出し、実装（プロバイダ）を差し替えうる機能を「1機能＝1サブパッケージ」で置きます（ADR-0091）。`knowledge.py`・`config.py`・`llm.py` などの基盤・配線はここに含めません。`tools` という名前を避けたのは MCP・LangGraph の「ツール」と紛らわしいためです。

## 構成

| 名前 | 説明 |
|---|---|
| [`assess/`](assess/README.md) | 蓄積した検索結果で質問に答えられるかを判定する十分性評価（ADR-0088 / ADR-0091）。 |
| [`__init__.py`](__init__.py) | パッケージ宣言。本パッケージの方針（1機能＝1サブパッケージ・階層を深くしない）を docstring に記す。 |
