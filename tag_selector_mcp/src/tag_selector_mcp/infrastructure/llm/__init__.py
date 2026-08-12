"""LLMClient 実装群（実装指示書 5.4 / ADR-0012, IMPL-202608101616 4.1 / ADR-0031）。

LLM_PROVIDER の値に応じて LLMClient 実装を選択するファクトリを提供する。
`lmstudio`（ローカル開発、既定）と `bedrock`（AWS 環境）に対応する。`openai` は将来対応。
"""

from __future__ import annotations

from .base import LLMClient
from .lmstudio import LMStudioLLMClient


def create_llm_client(
    provider: str,
    chat_url: str | None = None,
    chat_model: str | None = None,
    *,
    bedrock_model_id: str | None = None,
    bedrock_region: str | None = None,
) -> LLMClient:
    """LLM_PROVIDER に対応する LLMClient を生成する。

    Args:
        provider: "lmstudio"（既定）または "bedrock"。
        chat_url: lmstudio 時に必須（LMSTUDIO_CHAT_URL）。
        chat_model: lmstudio 時に必須（LMSTUDIO_CHAT_MODEL）。
        bedrock_model_id: bedrock 時に必須（BEDROCK_CHAT_MODEL_ID）。
        bedrock_region: bedrock 時に必須（BEDROCK_REGION）。
    """
    if provider == "lmstudio":
        if not chat_url or not chat_model:
            raise ValueError(
                "LLM_PROVIDER='lmstudio' には LMSTUDIO_CHAT_URL と "
                "LMSTUDIO_CHAT_MODEL が必要です。"
            )
        return LMStudioLLMClient(chat_url, chat_model)
    if provider == "bedrock":
        # boto3 依存を lmstudio 経路に持ち込まないよう、分岐内で遅延 import する。
        from .bedrock import BedrockLLMClient

        if not bedrock_model_id or not bedrock_region:
            raise ValueError(
                "LLM_PROVIDER='bedrock' には BEDROCK_CHAT_MODEL_ID と "
                "BEDROCK_REGION が必要です。"
            )
        return BedrockLLMClient(bedrock_model_id, bedrock_region)
    raise ValueError(
        f"unsupported LLM_PROVIDER '{provider}'. supported: 'lmstudio', 'bedrock'."
    )


__all__ = ["LLMClient", "LMStudioLLMClient", "create_llm_client"]
