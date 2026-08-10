"""ReAct エージェントの構築とシステムプロンプト（実装指示書 5.4 / T7 / ADR-0022）。"""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent

SYSTEM_PROMPT = """\
あなたはユーザーからの質問に答えるアシスタントです。以下の方針に従ってください。

1. まず select_tags を使って質問文に関連するタグを取得してください。
2. 取得したタグを使って search_knowledge を呼び出し、関連する社内QA情報を検索してください。
3. 検索結果に基づいて、質問に対する回答を生成してください。
4. select_tags が関連タグを返さなかった場合や、search_knowledge の検索結果が空だった場合は、
   その旨を踏まえて「関連する情報が見つかりませんでした」等の回答を返してください。
   存在しない情報を推測で作り出さないでください。
"""
# 6.1節で残存リスクとして記録した「LLMが期待順序で呼ばない可能性」への一次的なガードレールとして、
# システムプロンプトで呼び出し順序を明示する（要件定義書 Open Issue #6）。


def build_agent(llm, tools):
    """create_react_agent で ReAct エージェントを構築する。"""
    return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)
