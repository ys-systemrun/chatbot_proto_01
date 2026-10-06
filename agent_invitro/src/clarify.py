"""Bedrock (boto3) を使って情報不足時の逆質問文を生成するモジュール（ADR-0088 決定6 / 6.5節）。

Agentic 探索ループが反復上限まで探しても検索結果が0件だった場合、推測で回答せず、回答に必要な
具体的な情報をユーザーへ尋ねる。生成に失敗した場合は generate.py のシステムプロンプト ルール3
と同一の定型文へフォールバックする（F-6.5.3）。

summarize.py・condense.py・llm_tasks/assess/ と同型の構成（Bedrock Converse API 呼び出し、プロンプト
定数を自己完結で保持する）を踏襲する。
"""

from __future__ import annotations

import logging

import boto3

from .prompt_store import load_prompt

logger = logging.getLogger(__name__)

# generate.py のシステムプロンプト ルール3 と同一の定型文（F-6.5.3 のフォールバック先）。
FALLBACK_CLARIFICATION = (
    "申し訳ございません、ご提供いただいた情報が不足しています。より詳しい情報を入力してください。"
)

# 文面は agent_invitro/prompts/clarify.md（ADR-0099 §3）。
_SYSTEM_PROMPT = load_prompt("clarify")


def _build_user_content(
    question: str,
    original_text: str,
    tried_queries: list[str],
    missing: str,
) -> str:
    """system プロンプトを除いたユーザーメッセージ本文を構築する（F-6.5.2）。"""
    parts = [f"[ユーザーの発話]\n{original_text}"]
    if question and question.strip() != original_text.strip():
        parts.append(f"[会話文脈を踏まえた質問]\n{question}")
    tried = "\n".join(f"- {q}" for q in tried_queries) or "（なし）"
    parts.append(f"[検索で試したクエリ（いずれも0件）]\n{tried}")
    if missing:
        parts.append(f"[不足していると判定された観点]\n{missing}")
    return "\n\n".join(parts)


class ClarifyQuestionLLMBedrock:
    """Bedrock (boto3) で逆質問文を生成するクラス（ADR-0088 決定6）。"""

    def __init__(
        self,
        model_id: str,
        region_name: str = "ap-northeast-1",
        max_tokens: int = 1024,
    ) -> None:
        self._model_id = model_id
        self._max_tokens = max_tokens
        self._client = boto3.client("bedrock-runtime", region_name=region_name)

    def _invoke(self, system: str, user_content: str) -> str:
        response = self._client.converse(
            modelId=self._model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user_content}]}],
            inferenceConfig={"maxTokens": self._max_tokens},
        )
        blocks = response["output"]["message"]["content"]
        return "".join(b.get("text", "") for b in blocks)

    def clarify(
        self,
        question: str,
        original_text: str,
        tried_queries: list[str],
        missing: str = "",
    ) -> tuple[str, str]:
        """逆質問文を生成する。

        Returns:
            (clarification, prompt) — 逆質問の本文と LLM に渡したユーザーメッセージ本文。
            generate.py の generate() と戻り値の形を揃え、assistant メッセージの `input` に
            そのまま入れられるようにする（F-6.5.4）。

        フォールバック（F-6.5.3）: Bedrock 呼び出し失敗時・空出力時は FALLBACK_CLARIFICATION
        を返す。prompt は生成を試みた内容をそのまま返す（何を入力したかをログ・評価画面に残す）。
        """
        user_content = _build_user_content(
            question, original_text, tried_queries, missing
        )
        try:
            text = self._invoke(_SYSTEM_PROMPT.strip(), user_content).strip()
        except Exception:
            logger.exception("逆質問生成の Bedrock 呼び出しに失敗しました（定型文へフォールバック）")
            return FALLBACK_CLARIFICATION, user_content
        return (text or FALLBACK_CLARIFICATION), user_content
