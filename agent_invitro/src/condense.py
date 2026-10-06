"""Bedrock (boto3) を使って今回の発話を standalone な質問文へ言い換えるモジュール（ADR-0085）。

複数ターンにまたがる文脈依存の短い発話（例:「XXXという条件です」単体）では、
select_tags・search_knowledge のいずれも文脈を踏まえられない。本モジュールは
summary.content・未要約履歴・今回の発話から、それ単体で意味が通る言い換え質問
（condensed_query）を1件生成する。生成結果は select_tags の query と
search_knowledge の query の両方に同一の値として使う（ADR-0085 決定）。

summarize.py と同型の構成（Bedrock Converse API 呼び出し、プロンプト定数を自己完結で
保持する）を踏襲する。agent_invitro を web_backend から独立させる既存方針
（summarize.py 冒頭コメント参照）と一貫させる。
"""

from __future__ import annotations

from typing import Protocol

import boto3

from .prompt_store import load_prompt


class _MessageLike(Protocol):
    """condense() が要求する最小インタフェース（.role / .content を持つ任意の型）。

    server.py の pydantic Message をそのまま渡せるよう、具体的なクラスに依存しない。
    未要約履歴の order による絞り込みは呼び出し側（server.py）で行う。
    """

    role: str
    content: str


# 言い換え質問生成用のシステムプロンプト。summarize.py の _SYSTEM_PROMPT と同様に、
# 出力を成果物（質問文）そのものだけに制約する（前置き・説明・番号を含めない）。
# 文面は agent_invitro/prompts/condense.md（ADR-0099 §3）。
_SYSTEM_PROMPT = load_prompt("condense")


def _build_user_content(
    text: str,
    messages: list[_MessageLike],
    summary: str,
) -> str:
    """system プロンプトを除いたユーザーメッセージ本文を構築する。

    要約・直近履歴が無いセクションは省略し、常に「今回の発話」を末尾に置く。
    """
    parts = []
    if summary:
        parts.append(f"[会話の要約]\n{summary}")
    if messages:
        conversation = "\n".join(f"[{m.role}]: {m.content}" for m in messages)
        parts.append(f"[直近の会話履歴]\n{conversation}")
    parts.append(f"[今回の発話]\n{text}")
    return "\n\n".join(parts)


class CondenseQueryLLMBedrock:
    """Bedrock (boto3) を使って今回の発話を standalone な質問文へ言い換えるクラス。

    summarize.py の SummarizeLLMBedrock と同一の呼び出し構造（Converse API）を持つ。
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
        # Bedrock Converse API を使う（モデル非依存の統一フォーマット, summarize.py と同一方針）。
        response = self._client.converse(
            modelId=self._model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user_content}]}],
            inferenceConfig={"maxTokens": self._max_tokens},
        )
        blocks = response["output"]["message"]["content"]
        return "".join(b.get("text", "") for b in blocks)

    def condense(
        self,
        text: str,
        messages: list[_MessageLike],
        summary: str = "",
    ) -> str:
        """今回の発話（text）を standalone な質問文へ言い換えて返す（ADR-0085 決定2）。

        Args:
            text: 今回の発話（req.text）。
            messages: 未要約履歴（呼び出し側で order > summarized_upto に絞り込み済み）。
                      system ロールのメッセージは対象から除外する。
            summary: 既存の要約（summary.content）。

        フォールバック（ADR-0085 決定4）:
            未要約履歴・要約のいずれも存在しない場合（会話の最初のターン）、または
            Bedrock 呼び出しが失敗した場合は、text をそのまま condensed_query として返す。
        """
        turns = [m for m in messages if m.role != "system"]

        # 会話文脈が無い（最初のターン）ときは言い換えず、そのまま返す。
        if not turns and not summary:
            return text

        user_content = _build_user_content(text, turns, summary)
        try:
            result = self._invoke(_SYSTEM_PROMPT, user_content).strip()
        except Exception:
            return text
        # LLM が空文字を返した場合も元の発話へフォールバックする。
        return result or text
