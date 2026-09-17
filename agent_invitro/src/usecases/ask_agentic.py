"""`POST /ask-agentic` の実処理（ADR-0088 / ADR-0089）。

前段（condense → select_tags）を1回ずつ実行し、`graph/agentic_search.py` の探索ループ
（search → assess の周回）を回したうえで、`generate`（回答生成）または `clarify`（逆質問）で
応答を組み立てる。レスポンスのスキーマ・組み立て形式は `/ask-pipeline` と完全に同一であり
（ADR-0089 決定2・決定3）、探索の経過（trace）はレスポンスに含めずログにのみ出力する
（ADR-0089 決定4）。
"""

from __future__ import annotations

import logging
import uuid

import anyio.to_thread

from ..graph.agentic_search import OUTCOME_CLARIFY, build_agentic_search_graph
from ..main.api.schemas import Request, Response
from ..tags import build_alias_match_text
from . import conversation

logger = logging.getLogger(__name__)


async def ask_agentic(req: Request, components: dict) -> Response:
    """Agentic 探索ループで1ターン分の応答を組み立てる。

    Args:
        req: リクエスト。
        components: `main/api/dependencies.get_components()` が返す依存一式。
    """
    settings = components["settings"]
    model_id = settings.bedrock_chat_model_id
    max_iterations = max(1, settings.agentic_max_iterations)
    top_k = max(1, settings.agentic_search_top_k)

    conversation_id = req.conversation_id or str(uuid.uuid4())
    messages = list(req.messages)
    summary = req.summary

    messages, summary = await conversation.fold_summary_if_needed(
        components["summarizer"], messages, summary
    )

    order = conversation.next_order(messages)
    history = conversation.build_history(messages)

    # --- 前処理（/ask-pipeline と共通, F-6.2）---
    alias_match_text = build_alias_match_text(
        req.text, messages, summary.summarized_upto
    )
    condensed_query = await conversation.condense_query(
        components["condenser"], req.text, messages, summary
    )
    tag_names = await conversation.select_tag_names(
        components["tags_tool"],
        condensed_query,
        alias_match_text,
        settings.tag_selector_max_tags,
        settings.tag_selector_confidence_threshold,
    )
    logger.info(
        "[%s] agentic start tags=%d %s max_iterations=%d top_k=%d",
        conversation_id, len(tag_names), tag_names, max_iterations, top_k,
    )

    # --- Agentic 探索ループ（F-6.3）---
    graph = build_agentic_search_graph(
        components["search_tool"],
        components["assessor"],
        max_iterations=max_iterations,
        top_k=top_k,
        conversation_id=conversation_id,
    )
    state = await graph.ainvoke({
        "text": req.text,
        "condensed_query": condensed_query,
        "tags": tag_names,
        "current_query": condensed_query,
        "tried_queries": [],
        "results": [],
        "iteration": 0,
    })

    results = state.get("results", [])
    tried_queries = state.get("tried_queries", [])
    outcome = state.get("outcome", "answer")

    # --- 回答生成（F-6.4）または逆質問（F-6.5）---
    if outcome == OUTCOME_CLARIFY:
        context = ""
        answer, prompt = await anyio.to_thread.run_sync(
            components["clarifier"].clarify,
            condensed_query,
            req.text,
            tried_queries,
            state.get("assessment", {}).get("missing", ""),
        )
    else:
        context = conversation.build_context(results)
        # 回答生成のプロンプトは /ask-pipeline と同一のものを使う（F-6.4.2 / ADR-0088 決定8）。
        answer, prompt = await anyio.to_thread.run_sync(
            components["generator"].generate,
            context,
            req.text,
            summary.content,
            history,
        )

    logger.info(
        "[%s] agentic done iterations=%d accumulated=%d outcome=%s model=%s answer_len=%d",
        conversation_id,
        state.get("iteration", 0),
        len(results),
        outcome,
        model_id,
        len(answer),
    )

    messages.append(conversation.build_user_message(order, context, req.text))
    messages.append(
        conversation.build_assistant_message(order + 1, answer, prompt, model_id)
    )

    return Response(
        conversation_id=conversation_id,
        messages=messages,
        summary=summary,
    )
