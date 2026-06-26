"""LLM を使って類似検索向けクエリを生成するモジュール。"""
from __future__ import annotations

import requests

_SYSTEM_PROMPT = """\
あなたは検索クエリの最適化アシスタントです。
ユーザーの直近のメッセージと、これまでの会話の文脈（要約・履歴）を踏まえ、
ベクトル類似検索に適した単独の検索クエリを生成してください。

ルール:
- 会話の文脈を考慮し、指示語（「それ」「あれ」など）を具体的な内容に置き換えること
- 検索クエリのみを出力し、前置き・説明・句読点などは含めないこと
- 日本語で出力すること\
"""

_ROLE_LABEL = {"user": "User", "assistant": "Assistant"}


def _build_user_content(
    question: str,
    summary: str,
    history: list[dict] | None,
) -> str:
    parts = []

    if summary:
        parts.append(f"[会話の要約]\n{summary}")

    if history:
        lines = [
            f"{_ROLE_LABEL.get(m['role'], m['role'])}: {m['content']}"
            for m in history
        ]
        parts.append("[直近の会話]\n" + "\n".join(lines))

    parts.append(f"[直近のユーザーメッセージ]\n{question}")

    return "\n\n".join(parts)


class FormatQueryToEmbed:
    """会話の文脈を踏まえ、類似検索に適したクエリを LLM で生成するクラス。

    指示語の解消や文脈の補完を行い、単独で意味が通る検索クエリを返す。
    LLM 呼び出しが失敗した場合は元の question をそのまま返す。
    """

    def __init__(self, url: str, model_name: str) -> None:
        """
        Args:
            url:        LLM の chat completions エンドポイント URL。
            model_name: 使用するモデル名。
        """
        self._url = url
        self._model_name = model_name

    def format(
        self,
        question: str,
        summary: str = "",
        history: list[dict] | None = None,
    ) -> tuple[str, str]:
        """ユーザーの質問と会話コンテキストを基に、類似検索向けのクエリを返す。

        Args:
            question: 現在のユーザーの入力テキスト。
            summary:  要約済み会話の内容。空文字の場合は文脈なしとして扱う。
            history:  直近の会話履歴（{"role": ..., "content": ...} のリスト）。
                      None または空の場合は文脈なしとして扱う。

        Returns:
            (formatted_query, input_content) — 整形されたクエリと LLM に渡した入力テキスト。
            LLM 呼び出し失敗時は (question, input_content) を返す。
        """
        input_content = _build_user_content(question, summary, history)
        try:
            res = requests.post(
                self._url,
                json={
                    "model": self._model_name,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user",   "content": input_content},
                    ],
                },
            )
            formatted = res.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            formatted = question
        return formatted, input_content
