"""Chat モデルのビルダー（実装指示書 5.3 / T6 / ADR-0020, IMPL-202608101616 4.4 / ADR-0031, ADR-0033）。

llm_provider に応じて接続先を切り替える:
- "lmstudio"（既定, ローカル開発）: LM Studio の OpenAI 互換 API へ向けた ChatOpenAI。
- "bedrock"（AWS 環境）: langchain_aws.ChatBedrockConverse。

Settings オブジェクトを直接受け取らず、llm_provider に応じて必要な値を
プリミティブな引数として個別に受け取る。config.py への依存を持たない
（to_openai_base_url も config.py から本ファイルへ移設、ADR-0033）。

いずれも build_agent(graph/agent.py) の bind_tools() に対応した Tool Calling 対応モデルを返すため、
graph/agent.py 側の変更は不要。
"""

from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# LM Studio はキーを検証しないため、任意のダミー文字列を使う。
_DUMMY_API_KEY = "lm-studio"


def to_openai_base_url(chat_completions_url: str) -> str:
    """LMSTUDIO_CHAT_URL を langchain_openai.ChatOpenAI の base_url 形式へ変換する。

    config.py から移設（ADR-0033）。ロジックは変更しない。

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


def build_llm(
    llm_provider: str,
    *,
    lmstudio_chat_url: str | None = None,
    lmstudio_chat_model: str | None = None,
    bedrock_chat_model_id: str | None = None,
    bedrock_region: str | None = None,
):
    """llm_provider に応じた Chat モデルを構築する。

    - "lmstudio": ChatOpenAI（to_openai_base_url() 経由。既存実装のまま）。
                  lmstudio_chat_url / lmstudio_chat_model を使用する。
    - "bedrock":  langchain_aws.ChatBedrockConverse。bedrock_chat_model_id /
                  bedrock_region を使用する。認証情報の明示指定は行わず、
                  ECS タスクロールによる既定の認証情報チェーンに委ねる。
    """
    if llm_provider == "bedrock":
        # langchain_aws は bedrock 利用時のみ必要な依存であるため遅延 import する。
        from langchain_aws import ChatBedrockConverse

        return ChatBedrockConverse(
            model=bedrock_chat_model_id,
            region_name=bedrock_region,
            temperature=0,
        )

    return ChatOpenAI(
        base_url=to_openai_base_url(lmstudio_chat_url),
        model=lmstudio_chat_model,
        api_key=_DUMMY_API_KEY,
        temperature=0,
    )
