"""`/ask-pipeline`・`/ask-agentic` が共有する会話処理（ADR-0090 決定5 / F-6.7.5）。

要約畳み込み・`history` / `next_order` の算出・`context` 構築・前処理（言い換え質問生成と
タグ選定）をここに集約し、両ユースケースで重複実装しない。

ADR-0090 決定4 に従い `fastapi` に依存しない。boto3 の同期 API をスレッドプールで実行する
必要があるため、`fastapi.concurrency.run_in_threadpool` ではなくその実体である
`anyio.to_thread.run_sync` を直接使う（挙動は同一, N-8.5）。
"""

from __future__ import annotations

import logging

import anyio.to_thread

from ..main.api.schemas import Message, Summary
from ..tags import _extract_selected_tags

logger = logging.getLogger(__name__)

# 要約畳み込みの閾値と1回あたりの件数（web_backend の chat_controller と同一）。
SUMMARIZE_THRESHOLD = 15
SUMMARIZE_COUNT = 3


def summarize_oldest(
    summarizer,
    messages: list[Message],
    summary: Summary,
    n: int = SUMMARIZE_COUNT,
) -> tuple[list[Message], Summary]:
    """order の昇順で先頭 n 件を要約し、残りメッセージと更新後の Summary を返す。"""
    sorted_msgs = sorted(messages, key=lambda m: m.order)
    to_summarize = sorted_msgs[:n]
    rest = sorted_msgs[n:]

    new_text = summarizer.summarize(to_summarize, summary.content)

    return rest, Summary(
        content=new_text,
        summarized_upto=to_summarize[-1].order,
    )


async def fold_summary_if_needed(
    summarizer, messages: list[Message], summary: Summary
) -> tuple[list[Message], Summary]:
    """15件以上のとき、order が若い順に3件を要約して messages から除外する（F-6.1.3）。

    web_backend の `/ask-pipeline` と同一の閾値・件数。boto3 は同期 API のためスレッド
    プールで実行する。
    """
    if len(messages) < SUMMARIZE_THRESHOLD:
        return messages, summary
    return await anyio.to_thread.run_sync(
        summarize_oldest, summarizer, messages, summary
    )


def next_order(messages: list[Message]) -> int:
    """次に採番する order（既存の最大 order + 1、空なら 1）。"""
    return (max(m.order for m in messages) + 1) if messages else 1


def build_history(messages: list[Message]) -> list[dict] | None:
    """回答生成 LLM へ渡す会話履歴（order 昇順の role/content）。空なら None。"""
    return [
        {"role": m.role, "content": m.content}
        for m in sorted(messages, key=lambda m: m.order)
    ] or None


def unsummarized(messages: list[Message], summarized_upto: int) -> list[Message]:
    """まだ要約に畳み込まれていないメッセージ（order > summarized_upto）。"""
    return [m for m in messages if m.order > summarized_upto]


def build_context(results: list[dict]) -> str:
    """search_knowledge の結果からプロンプト用のコンテキスト文字列を構築する（F-6.4.1）。

    search_knowledge の出力スキーマ（title=QA タイトル / content=回答本文）に沿って整形する。
    """
    return "\n".join(
        f"Q: {r.get('title', '')}\nA: {r.get('content', '')}" for r in results
    )


def build_user_message(order: int, context: str, text: str) -> Message:
    """コンテキスト込みの user メッセージ（web_backend の content 形式と同一, F-6.1.4）。"""
    return Message(
        order=order,
        role="user",
        content=f"参考情報:\n{context}\n\n質問:\n{text}",
    )


def build_assistant_message(
    order: int, answer: str, prompt: str, model_id: str
) -> Message:
    """assistant メッセージ（input=LLM へ渡したプロンプト / evaluation=0 未評価, F-6.1.4）。"""
    return Message(
        order=order,
        role="assistant",
        content=answer,
        input=prompt,
        model=model_id,
        evaluation=0,
    )


async def condense_query(
    condenser, text: str, messages: list[Message], summary: Summary
) -> str:
    """言い換え質問（condensed_query）を生成する（ADR-0085 / F-6.2.2）。

    summary.content・未要約履歴・今回の発話から standalone な質問文を生成し、select_tags と
    search_knowledge の両方の query に同一の値を使う。会話の最初のターンや LLM 失敗時は text
    へフォールバックする（condense() 内で処理）。boto3 は同期 API のためスレッドプールで実行する。
    """
    turns = unsummarized(messages, summary.summarized_upto)
    condensed = await anyio.to_thread.run_sync(
        condenser.condense, text, turns, summary.content
    )
    logger.info("condensed_query=%r (req.text=%r)", condensed, text)
    return condensed


async def select_tag_names(
    tags_tool,
    condensed_query: str,
    alias_match_text: str,
    max_tags: int,
    confidence_threshold: float,
) -> list[str]:
    """select_tags を1回だけ呼び、選定されたタグ名のリストを返す（ADR-0086 / F-6.2.3）。

    失敗時は空集合として継続する（要件定義書6.4.1節）。ADR-0084 により会話タグ機構
    （クライアント由来タグとのマージ・継続判定）は廃止されており、毎ターン選び直したタグ集合を
    そのまま search_knowledge へ渡す。
    """
    try:
        raw_tags = await tags_tool.ainvoke({
            "query": condensed_query,
            "alias_match_text": alias_match_text,
            "max_tags": max_tags,
            "confidence_threshold": confidence_threshold,
        })
        selected = _extract_selected_tags(raw_tags)
    except Exception:
        logger.exception("select_tags failed")
        selected = []
    return [t["name"] for t in selected]
