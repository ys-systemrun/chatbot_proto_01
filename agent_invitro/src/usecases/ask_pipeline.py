"""`POST /ask-pipeline` の実処理（ADR-0043 0章「単発プロンプト生成方式」）。

再構成前は main/api/server.py の `_ask_impl` として実装されていたものを、HTTP 層から切り離した
もの（外部から観測できる挙動は不変, ADR-0090 決定7）。

「要約畳み込み → condensed_query 生成（ADR-0085）→ select_tags 1回（ADR-0086）→
search_knowledge 1回（ADR-0062/0084）→ 回答生成」という一本道の固定パイプライン。探索の結果を
受けて次の行動を決める Agentic な経路は `/ask-agentic`（usecases/ask_agentic.py, ADR-0088）に
分離されている。
"""

from __future__ import annotations

import logging
import uuid

import anyio.to_thread

from ..knowledge import search_knowledge
from ..main.api.schemas import Request, Response
from ..tags import build_alias_match_text
from . import conversation

logger = logging.getLogger(__name__)


async def ask_pipeline(req: Request, components: dict) -> Response:
    """単発プロンプト生成方式で1ターン分の応答を組み立てる。

    Args:
        req: リクエスト。
        components: `main/api/dependencies.get_components()` が返す依存一式。
    """
    settings = components["settings"]
    model_id = settings.bedrock_chat_model_id

    conversation_id = req.conversation_id or str(uuid.uuid4())
    messages = list(req.messages)
    summary = req.summary

    messages, summary = await conversation.fold_summary_if_needed(
        components["summarizer"], messages, summary
    )

    # 会話履歴と order を事前計算する。
    order = conversation.next_order(messages)
    history = conversation.build_history(messages)

    # Alias 一致（確定タグ）専用の生テキスト。今回の発話＋未要約履歴のうち user 発話を
    # 結合する（ADR-0086）。query（LLM 推論用）と別に、固定エラー文言を保持した生テキスト
    # に対して決定論的な Alias 一致を行うために渡す。
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

    # --- QA 類似検索（その場で選定したタグをそのまま渡す単一呼び出し, ADR-0084 / ADR-0062）---
    # top_k は現行どおり 3 固定とする。AGENTIC_SEARCH_TOP_K は Agentic ループ専用の設定であり
    # （ADR-0088 決定5）、本エンドポイントの外部挙動は再構成で変えない（ADR-0090 決定7）。
    results = await search_knowledge(
        components["search_tool"], condensed_query, tag_names, top_k=3
    )
    logger.info(
        "search_knowledge query=%r tags=%d hits=%d",
        condensed_query, len(tag_names), len(results),
    )
    context = conversation.build_context(results)

    messages.append(conversation.build_user_message(order, context, req.text))

    # LLM 回答生成（Bedrock）。boto3 は同期 API のためスレッドプールで実行する。
    answer, prompt = await anyio.to_thread.run_sync(
        components["generator"].generate,
        context,
        req.text,
        summary.content,
        history,
    )
    logger.info("bedrock generate model=%s answer_len=%d", model_id, len(answer))

    messages.append(
        conversation.build_assistant_message(
            order + 1,
            answer,
            prompt,
            model_id,
            release_id=conversation.release_id_of(components),
            ask_mode="pipeline",
        )
    )

    return Response(
        conversation_id=conversation_id,
        messages=messages,
        summary=summary,
    )
