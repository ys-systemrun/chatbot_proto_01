"""BedrockLLMClient（実装指示書 IMPL-202608101616 4.1 / ADR-0031）。

Amazon Bedrock の Converse API を用いてチャット補完を行う LLMClient 実装。
既存 LMStudioLLMClient と同一のインターフェース（complete(prompt: str) -> str）を満たすため、
呼び出し元（InferenceEngine, application/inference_engine.py）は変更不要。

認証情報は明示指定せず、boto3 の既定の認証情報チェーン（ECS Fargate タスクロール等）に委ねる
（IMPL-202608101616 3章）。
"""

from __future__ import annotations

from .base import LLMClient


class BedrockLLMClient(LLMClient):
    """Amazon Bedrock Converse API を用いてチャット補完を行う LLMClient 実装。"""

    def __init__(self, model_id: str, region_name: str):
        """
        Args:
            model_id: Bedrock 上のモデルID（例: Anthropic Claude 系。BEDROCK_CHAT_MODEL_ID）。
            region_name: Bedrock を呼び出す AWS リージョン（BEDROCK_REGION）。
        """
        # boto3 は bedrock 利用時のみ必要な依存であるため遅延 import する
        # （ローカル（lmstudio）動作時に boto3 未導入でも本モジュールを import できるようにする）。
        import boto3

        self._model_id = model_id
        self._client = boto3.client("bedrock-runtime", region_name=region_name)

    def complete(self, prompt: str) -> str:
        """Converse API で prompt を送信し、応答テキストをそのまま返す。

        既存 LMStudioLLMClient.complete() と同じくプレーンテキストを返すため、
        呼び出し元の JSON パースロジックはそのまま利用できる。
        """
        response = self._client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
        )
        return response["output"]["message"]["content"][0]["text"]
