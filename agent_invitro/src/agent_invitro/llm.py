"""LM Studio 接続用 Chat モデルのビルダー（実装指示書 5.3 / T6 / ADR-0020）。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from .config import Settings, to_openai_base_url

# LM Studio はキーを検証しないため、任意のダミー文字列を使う。
_DUMMY_API_KEY = "lm-studio"


def build_llm(settings: Settings) -> ChatOpenAI:
    """LM Studio の OpenAI 互換 Chat Completions API へ接続する ChatOpenAI を構築する。

    - base_url: to_openai_base_url(settings.lmstudio_chat_url)
    - model: settings.lmstudio_chat_model
    - api_key: LM Studio はキーを検証しないためダミー文字列
    - temperature=0: 実験の再現性を上げるため決定的寄りに設定（詳細設計で調整可）
    """
    return ChatOpenAI(
        base_url=to_openai_base_url(settings.lmstudio_chat_url),
        model=settings.lmstudio_chat_model,
        api_key=_DUMMY_API_KEY,
        temperature=0,
    )
