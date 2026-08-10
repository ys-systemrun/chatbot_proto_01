"""InferenceEngine（実装指示書 5.5 / T7 / 要件6.4）。

質問文・確定タグ・全候補タグからプロンプトを構築して LLM に投げ、応答（JSON想定）を
パースして SelectedTag のリストを返す。LM Studio のモデルは出力形式が安定しないことが
あるため、パース失敗時のフォールバック（空リストを返す）を必ず備える（11章）。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List

from ..infrastructure.llm.base import LLMClient
from ..models.tag import SelectedTag
from .retrieval_engine import RetrievalResult

logger = logging.getLogger(__name__)


_PROMPT_TEMPLATE = """\
あなたはタグ分類の専門家です。以下の質問に最も関連するタグを、与えられたタグ一覧の中から選んでください。

質問: {query}

タグ一覧:
{tag_lines}

既に同義語辞書との一致により確定しているタグ: {confirmed}

出力は以下のJSON形式のみとし、他の説明文は含めないでください。
{{"selected": [{{"tag_id": <id>, "score": <0.0から1.0の確信度>}}, ...]}}
"""


class InferenceEngine:
    def __init__(self, llm_client: LLMClient):
        self._llm_client = llm_client

    # ------------------------------------------------------------------ #
    # プロンプト構築
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_prompt(query: str, retrieval_result: RetrievalResult) -> str:
        tag_lines = "\n".join(
            f"- id={t.id}, name={t.name}, description={t.description or ''}"
            for t in retrieval_result.candidates
        )
        if retrieval_result.confirmed:
            confirmed = ", ".join(
                f"id={t.id}({t.name})" for t in retrieval_result.confirmed
            )
        else:
            confirmed = "なし"
        return _PROMPT_TEMPLATE.format(
            query=query, tag_lines=tag_lines, confirmed=confirmed
        )

    # ------------------------------------------------------------------ #
    # 応答パース（フォールバック付き）
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_response(text: str) -> List[dict]:
        """LLM応答から {"selected": [{"tag_id", "score"}, ...]} を取り出す。

        余分なテキストが混入していても、最初の JSON オブジェクトを抽出して解釈を試みる。
        解釈できない場合は空リストを返す（例外は送出しない）。
        """
        if not text:
            return []

        candidates = [text]
        # ```json ... ``` などのコードフェンス／前後テキストを剥がすため、
        # 最初の '{' から最後の '}' までを追加候補にする。
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start : end + 1])

        for raw in candidates:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            selected = data.get("selected") if isinstance(data, dict) else None
            if isinstance(selected, list):
                return selected

        logger.warning("failed to parse LLM response as JSON; returning empty result")
        return []

    # ------------------------------------------------------------------ #
    # 推論
    # ------------------------------------------------------------------ #
    def infer(
        self,
        query: str,
        retrieval_result: RetrievalResult,
        max_tags: int,
        confidence_threshold: float,
    ) -> List[SelectedTag]:
        prompt = self._build_prompt(query, retrieval_result)

        try:
            response_text = self._llm_client.complete(prompt)
        except Exception:
            # 接続失敗・タイムアウト等は呼び出し元（SelectTagsUseCase / ツールハンドラ）へ伝播する。
            logger.exception("LLM completion failed")
            raise

        raw_selected = self._parse_response(response_text)

        # id -> name の引き当てマップ（候補＝全タグから作る）
        name_by_id: Dict[int, str] = {
            t.id: t.name for t in retrieval_result.candidates
        }

        selected: List[SelectedTag] = []
        for item in raw_selected:
            if not isinstance(item, dict):
                continue
            tag_id = item.get("tag_id")
            score = item.get("score")
            if tag_id is None or score is None:
                continue
            try:
                tag_id = int(tag_id)
                score = float(score)
            except (TypeError, ValueError):
                continue
            name = name_by_id.get(tag_id)
            if name is None:
                # 候補に存在しない id は無視する（LLMの幻覚対策）
                continue
            if score < confidence_threshold:
                continue
            selected.append(SelectedTag(id=tag_id, name=name, score=score, path=[name]))

        selected.sort(key=lambda s: s.score, reverse=True)
        return selected[:max_tags]
