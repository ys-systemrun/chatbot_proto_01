# agent_invitro/src/graph — LangGraph のグラフ定義

LangGraph で組むエージェント／状態グラフを置きます。IPython 実験用の ReAct エージェント（ADR-0022）と、`/ask-agentic` が使う決定論的な探索ループ（ADR-0088）の2つです。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`agent.py`](agent.py) | `create_react_agent` で ReAct エージェントを組む `build_agent(llm, tools)`。システムプロンプトは `prompts/react_agent.md`。`main/ipython/main.py` から使う（HTTP 経路では使わない）。 |
| [`agentic_search.py`](agentic_search.py) | `search`（`search_knowledge` 1回）と `assess`（十分性評価 1回）を条件付きエッジで周回させる `StateGraph` を作る `build_agentic_search_graph()` と分岐判定 `_decide()`。回答生成／逆質問はグラフ外（`usecases/ask_agentic.py`）で行い、グラフは進む先を `outcome` で返すだけ（ADR-0088）。 |
