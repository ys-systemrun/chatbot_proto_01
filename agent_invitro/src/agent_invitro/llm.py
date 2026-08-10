"""Chat モデルのビルダー（実装指示書 5.3 / T6 / ADR-0020, IMPL-202608101616 4.4 / ADR-0031）。

settings.llm_provider に応じて接続先を切り替える:
- "lmstudio"（既定, ローカル開発）: LM Studio の OpenAI 互換 API へ向けた ChatOpenAI。
- "bedrock"（AWS 環境）: langchain_aws.ChatBedrockConverse。

いずれも build_agent(graph/agent.py) の bind_tools() に対応した Tool Calling 対応モデルを返すため、
graph/agent.py 側の変更は不要。
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from .config import Settings, to_openai_base_url

# LM Studio はキーを検証しないため、任意のダミー文字列を使う。
_DUMMY_API_KEY = "lm-studio"


def build_llm(settings: Settings):
    """settings.llm_provider に応じた Chat モデルを構築する。

    - "lmstudio": ChatOpenAI（to_openai_base_url() 経由。既存実装のまま）。
    - "bedrock":  langchain_aws.ChatBedrockConverse。認証情報の明示指定は行わず、
                  ECS タスクロールによる既定の認証情報チェーンに委ねる。
    """
    if settings.llm_provider == "bedrock":
        # langchain_aws は bedrock 利用時のみ必要な依存であるため遅延 import する。
        from langchain_aws import ChatBedrockConverse

        return ChatBedrockConverse(
            model=settings.bedrock_chat_model_id,
            region_name=settings.bedrock_region,
            temperature=0,
        )

    return ChatOpenAI(
        base_url=to_openai_base_url(settings.lmstudio_chat_url),
        model=settings.lmstudio_chat_model,
        api_key=_DUMMY_API_KEY,
        temperature=0,
    )
