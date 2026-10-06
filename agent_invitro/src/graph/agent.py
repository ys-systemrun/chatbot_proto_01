"""ReAct エージェントの構築とシステムプロンプト（実装指示書 5.4 / T7 / ADR-0022）。"""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from ..prompt_store import load_prompt

# 方式A（ReAct, ADR-0022）を維持したまま、「ツール呼び出しの省略（＝社内QAを参照しない一般回答）」を
# 抑止する一次ガードレールとして、常時のツール実行と検索結果への接地をシステムプロンプトで強く指示する
# （要件定義書 Open Issue #6。ベストエフォートであり100%保証ではない）。
# 文面は agent_invitro/prompts/react_agent.md（ADR-0099 §3）。
SYSTEM_PROMPT = load_prompt("react_agent")


def build_agent(llm, tools):
    """create_react_agent で ReAct エージェントを構築する。"""
    return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)
