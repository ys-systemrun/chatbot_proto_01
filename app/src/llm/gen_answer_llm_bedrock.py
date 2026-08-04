"""Bedrock (boto3) を使って回答を生成するクラス。GenerateAnswerLLM と同一インタフェース。"""
from __future__ import annotations

import json
import boto3

from .gen_answer_llm import _SYSTEM_PROMPT, _ROLE_LABEL


def _build_user_content(
    context: str,
    question: str,
    summary: str = "",
    history: list[dict] | None = None,
) -> str:
    """system プロンプトを除いたユーザーメッセージ本文を構築する。

    Bedrock Claude では system を別フィールドで渡すため、
    gen_answer_llm._build_prompt とは異なり system セクションを含まない。
    """
    parts = []

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


class GenerateAnswerLLMBedrock:
    """Bedrock (boto3) を使って回答を生成するクラス。

    GenerateAnswerLLM と同一のメソッドシグネチャを持つ。
    コンストラクタの引数のみ異なる（url/model_name → model_id/region_name）。
    """

    def __init__(
        self,
        model_id: str,
        region_name: str = "ap-northeast-1",
        max_tokens: int = 4096,
    ) -> None:
        self._model_id = model_id
        self._max_tokens = max_tokens
        self._client = boto3.client("bedrock-runtime", region_name=region_name)

    def _invoke(self, system: str, messages: list[dict]) -> str:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": messages,
        }
        response = self._client.invoke_model(
            modelId=self._model_id,
            body=json.dumps(body, ensure_ascii=False),
            contentType="application/json",
            accept="application/json",
        )
        return json.loads(response["body"].read())["content"][0]["text"]

    def generate_stateful(self, messages: list[dict]) -> str:
        """メッセージ履歴を渡して回答を生成する（ステートフル版）。

        messages に system ロールが含まれる場合は Bedrock の system フィールドに移動する。
        """
        system = " ".join(
            m["content"] for m in messages if m["role"] == "system"
        ) or _SYSTEM_PROMPT.strip()
        non_system = [m for m in messages if m["role"] != "system"]
        return self._invoke(system, non_system)

    def generate(
        self,
        context: str,
        question: str,
        summary: str = "",
        history: list[dict] | None = None,
    ) -> tuple[str, str]:
        """構造化プロンプトで回答を生成する。

        Returns:
            (answer, prompt) — 回答テキストと LLM に渡したユーザーメッセージ本文。
        """
        user_content = _build_user_content(context, question, summary, history)
        answer = self._invoke(
            _SYSTEM_PROMPT.strip(),
            [{"role": "user", "content": user_content}],
        )
        return answer, user_content
