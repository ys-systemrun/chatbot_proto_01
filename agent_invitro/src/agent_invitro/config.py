"""環境変数の読み込みと設定値の保持（実装指示書 5.1 / T4）。"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Settings:
    knowledge_mcp_url: str
    tag_selector_mcp_url: str
    lmstudio_chat_url: str  # 例: http://host.docker.internal:1234/v1/chat/completions（既存形式）
    lmstudio_chat_model: str


def load_settings() -> Settings:
    """os.environ から必須の環境変数を読み込む。

    KNOWLEDGE_MCP_URL / TAG_SELECTOR_MCP_URL / LMSTUDIO_CHAT_URL / LMSTUDIO_CHAT_MODEL
    を読み込む。未設定の必須項目があれば起動時に例外を発生させる。
    """
    required = {
        "knowledge_mcp_url": "KNOWLEDGE_MCP_URL",
        "tag_selector_mcp_url": "TAG_SELECTOR_MCP_URL",
        "lmstudio_chat_url": "LMSTUDIO_CHAT_URL",
        "lmstudio_chat_model": "LMSTUDIO_CHAT_MODEL",
    }

    values: dict[str, str] = {}
    missing: list[str] = []
    for field, env_name in required.items():
        raw = os.environ.get(env_name)
        if not raw:
            missing.append(env_name)
        else:
            values[field] = raw

    if missing:
        raise RuntimeError(
            "必須の環境変数が未設定です: " + ", ".join(missing)
        )

    return Settings(**values)


def to_openai_base_url(chat_completions_url: str) -> str:
    """LMSTUDIO_CHAT_URL を langchain_openai.ChatOpenAI の base_url 形式へ変換する。

    既存の LMSTUDIO_CHAT_URL は末尾に '/chat/completions' を含む完全なエンドポイント形式
    （例: http://host.docker.internal:1234/v1/chat/completions）だが、
    ChatOpenAI の base_url は 'v1' までのルート
    （例: http://host.docker.internal:1234/v1）を要求する。
    末尾の '/chat/completions' を取り除いて返す。
    想定外の形式の場合は警告ログを出し、そのまま返す（フォールバック）。
    """
    url = chat_completions_url.rstrip("/")
    suffix = "/chat/completions"
    if url.endswith(suffix):
        return url[: -len(suffix)]

    logger.warning(
        "LMSTUDIO_CHAT_URL が想定形式（末尾 '/chat/completions'）ではありません。"
        "そのまま base_url として使用します: %s",
        chat_completions_url,
    )
    return chat_completions_url
