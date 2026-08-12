"""環境変数の読み込みと設定値の保持（実装指示書 5.1 / T4, ADR-0033）。

本モジュールの責務は「環境変数の読み込みと Settings の保持」のみ。
to_openai_base_url() は LLM 層固有の関心事であるため llm.py へ移設した（ADR-0033）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    knowledge_mcp_url: str
    tag_selector_mcp_url: str
    llm_provider: str  # "lmstudio"（既定）または "bedrock"（IMPL-202608101616 4.4 / ADR-0031）
    lmstudio_chat_url: str | None = None  # lmstudio 時のみ必須（既存形式の完全URL）
    lmstudio_chat_model: str | None = None  # lmstudio 時のみ必須
    bedrock_chat_model_id: str | None = None  # bedrock 時のみ必須（BEDROCK_CHAT_MODEL_ID）
    bedrock_region: str | None = None  # bedrock 時のみ必須（BEDROCK_REGION）


def load_settings() -> Settings:
    """os.environ から必須の環境変数を読み込む（IMPL-202608101616 4.4）。

    KNOWLEDGE_MCP_URL / TAG_SELECTOR_MCP_URL は常に必須。
    LLM_PROVIDER（既定 "lmstudio"）に応じて追加の必須項目が決まる:
      - "lmstudio": LMSTUDIO_CHAT_URL / LMSTUDIO_CHAT_MODEL
      - "bedrock":  BEDROCK_CHAT_MODEL_ID / BEDROCK_REGION
    未設定の必須項目があれば起動時に例外を発生させる。
    """
    llm_provider = os.environ.get("LLM_PROVIDER", "lmstudio")

    required = {
        "knowledge_mcp_url": "KNOWLEDGE_MCP_URL",
        "tag_selector_mcp_url": "TAG_SELECTOR_MCP_URL",
    }
    if llm_provider == "bedrock":
        required.update(
            {
                "bedrock_chat_model_id": "BEDROCK_CHAT_MODEL_ID",
                "bedrock_region": "BEDROCK_REGION",
            }
        )
    else:
        required.update(
            {
                "lmstudio_chat_url": "LMSTUDIO_CHAT_URL",
                "lmstudio_chat_model": "LMSTUDIO_CHAT_MODEL",
            }
        )

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

    return Settings(llm_provider=llm_provider, **values)
