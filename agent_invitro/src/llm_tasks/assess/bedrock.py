"""Bedrock (boto3) による十分性評価の具象実装（ADR-0088 決定2 / ADR-0091 決定2）。

summarize.py の SummarizeLLMBedrock と同一の呼び出し構造（Converse API）を持つ。
`Settings` を受け取らずプリミティブを引数で受け取る（ADR-0033 / ADR-0091 決定4）。
"""

from __future__ import annotations

import logging

import boto3

from .base import DEGRADED_ASSESSMENT, SufficiencyAssessor
from .parsing import parse_assessment
from .prompts import SYSTEM_PROMPT, build_user_content

logger = logging.getLogger(__name__)


class SufficiencyAssessorBedrock(SufficiencyAssessor):
    """Bedrock (boto3) で検索結果の十分性を評価するクラス。"""

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
        response = self._client.converse(
            modelId=self._model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user_content}]}],
            inferenceConfig={"maxTokens": self._max_tokens},
        )
        blocks = response["output"]["message"]["content"]
        return "".join(b.get("text", "") for b in blocks)

    def assess(
        self, question: str, results: list[dict], tried_queries: list[str]
    ) -> dict:
        """十分性を評価し `{"sufficient", "missing", "next_query"}` を返す。

        フォールバック（F-6.3.8）: Bedrock 呼び出しが失敗した場合、および出力を JSON として
        解釈できない場合は `sufficient=True` を返し、ループを抜けさせる（＝現行 /ask-pipeline
        と同等の単発検索の挙動へ縮退する）。失敗は生出力の先頭とともにログへ残す（F-6.6.2）。
        例外はここで捕捉し、呼び出し側へ送出しない（ADR-0091 決定3の契約）。
        """
        user_content = build_user_content(question, results, tried_queries)
        try:
            raw = self._invoke(SYSTEM_PROMPT, user_content)
        except Exception:
            logger.exception("十分性評価の Bedrock 呼び出しに失敗しました（sufficient=true とみなします）")
            return dict(DEGRADED_ASSESSMENT)

        parsed = parse_assessment(raw)
        if parsed is None:
            logger.warning(
                "十分性評価の出力をパースできませんでした（sufficient=true とみなします）: head=%s",
                repr(raw)[:300],
            )
            return dict(DEGRADED_ASSESSMENT)
        return parsed
