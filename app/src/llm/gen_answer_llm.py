"""LLM を使って回答を生成するクラス。"""
from __future__ import annotations

import requests

_SYSTEM_PROMPT = """\
あなたは当社製品専門の優秀なカスタマーサポートAIです。
顧客からのトラブルや操作方法に関する質問に対し、参考情報をもとにルールに沿って解決策を提案してください。

応答のルール:
1. まずは「お問い合わせいただきありがとうございます」と挨拶してください。
2. 参考情報に回答に必要な情報が含まれる場合は、解決策はステップ・バイ・ステップで手順を分けて提示し、回答の最後には「こちらの方法で解決しない場合は、お手数ですが有人サポートまでご連絡ください」と添えてください。
3. 問い合わせ内容があいまいで参考情報に回答に必要な情報が得られなかった場合は、「申し訳ございません、ご提供いただいた情報が不足しています。より詳しい情報を入力してください。」と回答してください。
4. 問い合わせ内容が当社製品と関係がない場合は、「申し訳ございません、当社の製品に関する操作方法やトラブルシューティングの範疇を超えるため、現在お手持ちの情報からはお答えすることができませんでした。」と回答してください。
"""

_ROLE_LABEL = {"user": "User", "assistant": "Assistant"}


def _build_prompt(
    context: str,
    question: str,
    summary: str = "",
    history: list[dict] | None = None,
) -> str:
    parts = [f"# System\n{_SYSTEM_PROMPT.strip()}"]

    if summary:
        parts.append(f"# Conversation Summary\n{summary}")

    if history:
        lines = [
            f"{_ROLE_LABEL.get(m['role'], m['role'])}: {m['content']}"
            for m in history
        ]
        parts.append("# Recent Conversation\n" + "\n".join(lines))

    parts.append(f"# Retrieved Knowledge\n{context}")
    parts.append(f"# Current User Message\n{question}")

    return "\n\n".join(parts)


class GenerateAnswerLLM:
    """コンテキストと質問から LLM で回答を生成するクラス。"""

    def __init__(self, url: str, model_name: str) -> None:
        self._url = url
        self._model_name = model_name

    def generate_stateful(self, messages: list[dict]) -> str:
        """メッセージ履歴を渡して回答を生成する（ステートフル版）。"""
        res = requests.post(
            self._url,
            json={"model": self._model_name, "messages": messages},
        )
        return res.json()["choices"][0]["message"]["content"]

    def generate(
        self,
        context: str,
        question: str,
        summary: str = "",
        history: list[dict] | None = None,
    ) -> tuple[str, str]:
        """構造化プロンプトで回答を生成する。

        Returns:
            (answer, prompt) — 回答テキストと LLM に渡したプロンプト。
        """
        prompt = _build_prompt(context, question, summary, history)
        res = requests.post(
            self._url,
            json={
                "model": self._model_name,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        answer = res.json()["choices"][0]["message"]["content"]
        return answer, prompt
