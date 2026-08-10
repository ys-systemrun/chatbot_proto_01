"""LLMClient 実装群（実装指示書 5.4 / ADR-0012）。

LLM_PROVIDER の値に応じて LLMClient 実装を選択するファクトリを提供する。
MVP では `lmstudio` のみ実装。`bedrock` / `openai` は将来 LLMClient 実装を追加して対応する。
"""

from __future__ import annotations

from .base import LLMClient
from .lmstudio import LMStudioLLMClient


def create_llm_client(provider: str, chat_url: str, chat_model: str) -> LLMClient:
    """LLM_PROVIDER に対応する LLMClient を生成する。"""
    if provider == "lmstudio":
        return LMStudioLLMClient(chat_url, chat_model)
    raise ValueError(
        f"unsupported LLM_PROVIDER '{provider}'. "
        "MVP supports only 'lmstudio' (ADR-0012)."
    )


__all__ = ["LLMClient", "LMStudioLLMClient", "create_llm_client"]
