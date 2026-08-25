"""Bedrock (boto3) を使って会話履歴を要約するクラス。SummarizeLLM と同一インタフェース。"""
from __future__ import annotations

import boto3

from src.models.stateless.message import Message
from .summarize_llm import _SYSTEM_PROMPT, _SYSTEM_PROMPT_WITH_EXISTING


class SummarizeLLMBedrock:
    """Bedrock (boto3) を使って会話の Message 履歴を短いテキストに要約するクラス。

    SummarizeLLM と同一のメソッドシグネチャを持つ。
    コンストラクタの引数のみ異なる（url/model_name → model_id/region_name）。
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
        # Bedrock Converse API を使う（モデル非依存の統一フォーマット, gen_answer_llm_bedrock.py と同一方針）。
        response = self._client.converse(
            modelId=self._model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user_content}]}],
            inferenceConfig={"maxTokens": self._max_tokens},
        )
        blocks = response["output"]["message"]["content"]
        return "".join(b.get("text", "") for b in blocks)

    def summarize(self, messages: list[Message], summary: str = "") -> str:
        """Message のリストを受け取り、会話全体を3文程度に要約して返す。

        system ロールのメッセージは要約対象から除外する。
        要約できる内容がない場合や Bedrock 呼び出しが失敗した場合は空文字列を返す。
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
