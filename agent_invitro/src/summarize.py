"""Bedrock (boto3) を使って会話履歴を要約するモジュール（IMPL-202608241104 T5, ADR-0043）。

web_backend/src/llm/summarize_llm_bedrock.py の SummarizeLLMBedrock と同一の
boto3 bedrock-runtime invoke_model 呼び出し構造を複製したもの（ADR-0016〜0018）。
agent_invitro を web_backend から独立させるため、プロンプト定数もここに複製して自己完結させる。
"""

from __future__ import annotations

from typing import Protocol

import boto3


class _MessageLike(Protocol):
    """summarize() が要求する最小インタフェース（.role / .content を持つ任意の型）。

    server.py の pydantic Message をそのまま渡せるよう、具体的なクラスに依存しない。
    """

    role: str
    content: str


# web_backend/src/llm/summarize_llm.py と同一のプロンプト（複製）。
_SYSTEM_PROMPT = """\
以下はユーザーとAIアシスタントの会話履歴です。
この会話の内容を3文程度の日本語で要約してください。
要約以外の文字（前置き・説明・番号など）は含めないこと。\
"""

_SYSTEM_PROMPT_WITH_EXISTING = """\
以下はユーザーとAIアシスタントの会話履歴です。
「既存の要約」を踏まえたうえで、「追加の会話履歴」の内容も含めた全体を3文程度の日本語で要約してください。
要約以外の文字（前置き・説明・番号など）は含めないこと。\
"""


class SummarizeLLMBedrock:
    """Bedrock (boto3) を使って会話の Message 履歴を短いテキストに要約するクラス。

    web_backend の同名クラスと同一のメソッドシグネチャ・呼び出し構造を持つ。
    """

    def __init__(
        self,
        model_id: str,
        region_name: str = "ap-northeast-1",
        max_tokens: int = 512,
    ) -> None:
        self._model_id = model_id
        self._max_tokens = max_tokens
        self._client = boto3.client("bedrock-runtime", region_name=region_name)

    def _invoke(self, system: str, user_content: str) -> str:
        # Bedrock Converse API を使う（モデル非依存の統一フォーマット, generate.py と同一方針）。
        response = self._client.converse(
            modelId=self._model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user_content}]}],
            inferenceConfig={"maxTokens": self._max_tokens},
        )
        blocks = response["output"]["message"]["content"]
        return "".join(b.get("text", "") for b in blocks)

    def summarize(self, messages: list[_MessageLike], summary: str = "") -> str:
        """Message のリストを受け取り、会話全体を3文程度に要約して返す。

        system ロールのメッセージは要約対象から除外する。
        要約できる内容がない場合や Bedrock 呼び出しが失敗した場合は既存の summary を返す。
        """
        turns = [m for m in messages if m.role != "system"]
        if not turns:
            return summary

        conversation = "\n".join(f"[{m.role}]: {m.content}" for m in turns)

        if summary:
            system_prompt = _SYSTEM_PROMPT_WITH_EXISTING
            user_content = (
                f"[既存の要約]\n{summary}\n\n"
                f"[追加の会話履歴]\n{conversation}"
            )
        else:
            system_prompt = _SYSTEM_PROMPT
            user_content = conversation

        try:
            return self._invoke(system_prompt, user_content).strip()
        except Exception:
            return summary
