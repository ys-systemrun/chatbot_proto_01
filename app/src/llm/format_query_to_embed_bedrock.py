"""Bedrock (boto3) を使って検索クエリを生成するクラス。FormatQueryToEmbed と同一インタフェース。"""
from __future__ import annotations

import json
import boto3

from .format_query_to_embed import _SYSTEM_PROMPT, _build_user_content


class FormatQueryToEmbedBedrock:
    """Bedrock (boto3) を使って類似検索向けクエリを生成するクラス。

    FormatQueryToEmbed と同一のメソッドシグネチャを持つ。
    コンストラクタの引数のみ異なる（url/model_name → model_id/region_name）。
    """

    def __init__(
        self,
        model_id: str,
        region_name: str = "ap-northeast-1",
        max_tokens: int = 256,
    ) -> None:
        self._model_id = model_id
        self._max_tokens = max_tokens
        self._client = boto3.client("bedrock-runtime", region_name=region_name)

    def format(
        self,
        question: str,
        summary: str = "",
        history: list[dict] | None = None,
    ) -> tuple[str, str]:
        """ユーザーの質問と会話コンテキストを基に、類似検索向けのクエリを返す。

        Returns:
            (formatted_query, input_content) — 整形されたクエリと LLM に渡した入力テキスト。
            Bedrock 呼び出し失敗時は (question, input_content) を返す。
        """
        input_content = _build_user_content(question, summary, history)
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self._max_tokens,
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": input_content}],
        }
        try:
            response = self._client.invoke_model(
                modelId=self._model_id,
                body=json.dumps(body, ensure_ascii=False),
                contentType="application/json",
                accept="application/json",
            )
            formatted = json.loads(response["body"].read())["content"][0]["text"].strip()
        except Exception:
            formatted = question
        return formatted, input_content
