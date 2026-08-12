"""Phase 1 スモークテスト（実装指示書 4.2 / T3 / 要件 Open Issue #3）。

LM Studio の OpenAI 互換 Chat Completions API に対し、ダミーのツール定義を bind_tools() で
束縛したリクエストを送り、モデルが構造化された tool_calls 形式で応答できるかを確認する。

手順:
1. config.load_settings() で LMSTUDIO_CHAT_URL / LMSTUDIO_CHAT_MODEL を取得する。
2. llm.build_llm() で ChatOpenAI インスタンスを構築する。
3. ダミーツール get_weather(city) を bind_tools() で束縛する。
4. 「東京の天気を教えて」のようにツールを呼ぶべき問い合わせを invoke する。
5. 返ってきた AIMessage の tool_calls が空でないことを確認する。
6. 結果（対応/非対応）を標準出力に出力する。

実行:
    docker compose exec agent_invitro python -m scripts.check_tool_calling
    または
    docker compose exec agent_invitro python agent_invitro/scripts/check_tool_calling.py
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent_invitro.config import load_settings
from agent_invitro.llm import build_llm


class GetWeather(BaseModel):
    """指定した都市の現在の天気を取得する。"""

    city: str = Field(description="天気を知りたい都市名")


def main() -> None:
    settings = load_settings()
    llm = build_llm(
        llm_provider=settings.llm_provider,
        lmstudio_chat_url=settings.lmstudio_chat_url,
        lmstudio_chat_model=settings.lmstudio_chat_model,
        bedrock_chat_model_id=settings.bedrock_chat_model_id,
        bedrock_region=settings.bedrock_region,
    )
    llm_with_tools = llm.bind_tools([GetWeather])

    query = "東京の天気を教えて"
    print(f"[model] {settings.lmstudio_chat_model}")
    print(f"[query] {query}")

    response = llm_with_tools.invoke(query)
    tool_calls = getattr(response, "tool_calls", None) or []

    print(f"[tool_calls] {tool_calls}")
    print(f"[content] {response.content!r}")

    if tool_calls:
        print("RESULT: 対応（Tool Calling 対応。構造化された tool_calls を取得できた）")
    else:
        print("RESULT: 非対応（tool_calls が空。実装指示書 4.3 節の代替方針を検討すること）")


if __name__ == "__main__":
    main()
