"""コンポーネントの遅延初期化・DI（ADR-0090 決定6 / F-6.7.6）。

再構成前は main/api/server.py の `_components` / `_init_lock` / `_get_components()` として
実装されていたもの。`load_settings()` は必須環境変数が無いと例外を送出するため、import 時では
なく最初のリクエスト到達時に一度だけ構築してキャッシュする（import 時に副作用を持たない,
ADR-0043 T9）。search_knowledge ツールの取得は非同期であるため `asyncio.Lock` で初期化競合を
防ぐ。

`load_settings()` の結果はここでプリミティブへ展開して各コンポーネントへ渡す
（`Settings` を下位モジュールへ直接渡さない, ADR-0033）。
"""

from __future__ import annotations

import asyncio
import logging

from ...clarify import ClarifyQuestionLLMBedrock
from ...condense import CondenseQueryLLMBedrock
from ...config import load_settings
from ...generate import GenerateAnswerLLMBedrock
from ...llm_tasks.assess import SufficiencyAssessorBedrock
from ...mcp_clients.client import build_mcp_client, load_tools
from ...summarize import SummarizeLLMBedrock

logger = logging.getLogger(__name__)

_components: dict | None = None
_init_lock = asyncio.Lock()


async def get_components() -> dict:
    """依存一式（settings / MCP ツール / Bedrock クライアント群）を返す。初回のみ構築する。"""
    global _components
    if _components is not None:
        return _components

    async with _init_lock:
        if _components is not None:  # ロック待機中に他コルーチンが初期化済みの場合
            return _components

        settings = load_settings()
        if settings.llm_provider != "bedrock":
            # 本サーバーは AWS 環境（Bedrock）専用（ADR-0043）。lmstudio 設定では起動しない。
            raise RuntimeError(
                "agent_invitro HTTP サーバーは LLM_PROVIDER=bedrock でのみ動作します"
                f"（現在: {settings.llm_provider}）"
            )

        mcp_client = build_mcp_client(
            tag_selector_mcp_url=settings.tag_selector_mcp_url,
            knowledge_mcp_url=settings.knowledge_mcp_url,
        )
        tools = await load_tools(mcp_client)
        search_tool = next(
            (t for t in tools if getattr(t, "name", None) == "search_knowledge"),
            None,
        )
        if search_tool is None:
            raise RuntimeError(
                "Knowledge MCP に search_knowledge ツールが見つかりません"
            )

        tags_tool = next(
            (t for t in tools if getattr(t, "name", None) == "select_tags"),
            None,
        )
        if tags_tool is None:
            raise RuntimeError(
                "Tag Selector MCP に select_tags ツールが見つかりません"
            )

        model_id = settings.bedrock_chat_model_id
        region = settings.bedrock_region

        # 十分性評価・逆質問生成のモデルは BEDROCK_CHAT_MODEL_ID を共用する
        # （専用の環境変数は設けない, ADR-0088 結果・影響）。
        _components = {
            "settings": settings,
            "mcp_client": mcp_client,
            "search_tool": search_tool,
            "tags_tool": tags_tool,
            "summarizer": SummarizeLLMBedrock(model_id=model_id, region_name=region),
            "generator": GenerateAnswerLLMBedrock(model_id=model_id, region_name=region),
            "condenser": CondenseQueryLLMBedrock(model_id=model_id, region_name=region),
            "assessor": SufficiencyAssessorBedrock(model_id=model_id, region_name=region),
            "clarifier": ClarifyQuestionLLMBedrock(model_id=model_id, region_name=region),
        }
        logger.info("agent_invitro components initialized (provider=bedrock)")
        return _components
