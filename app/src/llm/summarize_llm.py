"""会話履歴を LLM で要約するモジュール。"""
from __future__ import annotations

import requests

from src.models.conversation_state.message import Message

_SYSTEM_PROMPT = """\
以下はユーザーとAIアシスタントの会話履歴です。
この会話の内容を3文程度の日本語で要約してください。
要約以外の文字（前置き・説明・番号など）は含めないこと。\
"""


class SummarizeLLM:
    """LLM を使って会話の Message 履歴を短いテキストに要約するクラス。

    `LLMKeywordExtractor` や `LLMRelevanceStrategy` と同じ呼び出しパターンを使用する。
    LLM 呼び出しに失敗した場合は空文字列を返し、処理を止めない。
    """

    def __init__(self, url: str, model_name: str) -> None:
        """
        Args:
            url:        LLM の chat completions エンドポイント URL。
                        例: ``"http://host.docker.internal:1234/v1/chat/completions"``
            model_name: 使用するモデル名。
        """
        self._url = url
        self._model_name = model_name

    def summarize(self, messages: list[Message]) -> str:
        """Message のリストを受け取り、会話全体を3文程度に要約して返す。

        system ロールのメッセージは要約対象から除外する。
        要約できる内容がない場合や LLM 呼び出しが失敗した場合は空文字列を返す。

        Args:
            messages: 要約対象の Message リスト（ConversationState.messages で取得できる）。

        Returns:
            要約テキスト。失敗時は空文字列。
        """
        turns = [m for m in messages if m.role != "system"]
        if not turns:
            return ""

        conversation = "\n".join(
            f"[{m.role}]: {m.content}" for m in turns
        )

        try:
            res = requests.post(
                self._url,
                json={
                    "model": self._model_name,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user",   "content": conversation},
                    ],
                },
            )
            return res.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return ""
