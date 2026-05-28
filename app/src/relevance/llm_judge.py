from __future__ import annotations

import requests

from .base import RelevanceStrategy

_RELEVANCE_PROMPT = """\
以下の参考情報はユーザーの質問に答えるために関連していますか？

質問:
{question}

参考情報:
{context}

参考情報が質問に関連している場合は「はい」、関連していない場合は「いいえ」とだけ答えてください。\
"""


class LLMRelevanceStrategy(RelevanceStrategy):
    """LLM に適合判定を委ねるストラテジー。"""

    def __init__(self, url: str, model: str) -> None:
        self._url = url
        self._model = model

    def is_relevant(self, question: str, results: list) -> bool:
        if not results:
            return False

        context = "\n".join(
            f"Q_similar: {r[0]}\nA_original: {r[1]}" for r in results
        )
        prompt = _RELEVANCE_PROMPT.format(question=question, context=context)

        try:
            res = requests.post(
                self._url,
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            answer = res.json()["choices"][0]["message"]["content"].strip()
            return "はい" in answer
        except Exception:
            # LLM 呼び出しに失敗した場合は適合とみなしてフォールバック
            return True
