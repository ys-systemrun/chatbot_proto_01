"""agent_invitro 常駐 HTTP サーバー（IMPL-202608241104 T2〜T4, ADR-0043）。

AWS 環境でのみ Uvicorn 起動する FastAPI アプリ。web_backend の /ask-sl と同一契約の
エンドポイントを提供し、admin_ui からの中継先となる（ADR-0045）。

- GET  /health : プロセス生存確認のみ（DB・MCP への到達性チェックは行わない, T2）。
- POST /ask-sl : Request{conversation_id, text, messages, summary}
                 → Response{conversation_id, messages, summary}（要件定義書6章と同一契約, T3）。

回答生成は 0章の決定に従い「単発プロンプト生成方式」を採る:
既存の graph/agent.py の ReAct エージェントは経由せず、Knowledge MCP の search_knowledge を
直接呼び出してコンテキストを作り（T4）、Bedrock invoke_model で要約・回答生成する（T5/T6）。

本モジュールは conversation データベースへは一切アクセスしない（ADR-0043 / T8）。評価機能は
admin_ui 側の責務であり、ここでは会話生成のみを担う。既存の main/ipython/main.py（IPython 用
エントリポイント）とは独立しており、import 時の副作用（load_settings 等）を持たない（T9）。
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ...config import load_settings
from ...generate import GenerateAnswerLLMBedrock
from ...mcp_clients.client import build_mcp_client, load_tools
from ...summarize import SummarizeLLMBedrock
from ...tags import (
    _extract_selected_tags,
    _mcp_result_to_dicts,
    compute_conversation_tags,
    search_with_merged_tags,
)

# INFO/ERROR ログを CloudWatch（stdout/stderr）へ確実に流す。uvicorn の既定設定は本モジュールの
# ロガーを構成しないため、明示的に basicConfig する（未構成時のみ有効）。
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()


# ---------------------------------------------------------------------------
# Contract（web_backend/main/main_stateless.py と同一, 要件定義書6章）
# ---------------------------------------------------------------------------
class Message(BaseModel):
    order: int
    role: str
    content: str
    input: str | None = None        # assistant: LLM に渡したプロンプト
    model: str | None = None        # assistant: 使用モデル名
    evaluation: int | None = None   # user: null / assistant: 0=未評価 1=good 2=bad


class Summary(BaseModel):
    content: str
    summarized_upto: int


class ConversationTag(BaseModel):
    id: int
    name: str
    score: float
    missed_turns: int


class Request(BaseModel):
    conversation_id: str | None = None  # None の場合はサーバー側で新規発行
    text: str
    messages: list[Message]
    summary: Summary
    tags: list[ConversationTag] | None = None   # 会話タグ（IMPL-202608261345 T8 / ADR-0056）


class Response(BaseModel):
    conversation_id: str
    messages: list[Message]
    summary: Summary
    tags: list[ConversationTag] = []   # agent_invitro は必ず算出済みの値を返すためデフォルト[]でよい


# ---------------------------------------------------------------------------
# コンポーネントの遅延初期化（import 時副作用を避ける, T9 / Open Issue #6）
# ---------------------------------------------------------------------------
# load_settings() は必須環境変数が無いと例外を送出するため、import 時ではなく最初の
# リクエスト到達時に一度だけ構築してキャッシュする。search_knowledge ツールの取得は
# 非同期であるため asyncio.Lock で初期化競合を防ぐ。
_components: dict | None = None
_init_lock = asyncio.Lock()


async def _get_components() -> dict:
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

        summarizer = SummarizeLLMBedrock(
            model_id=settings.bedrock_chat_model_id,
            region_name=settings.bedrock_region,
        )
        generator = GenerateAnswerLLMBedrock(
            model_id=settings.bedrock_chat_model_id,
            region_name=settings.bedrock_region,
        )

        _components = {
            "settings": settings,
            "mcp_client": mcp_client,
            "search_tool": search_tool,
            "tags_tool": tags_tool,
            "summarizer": summarizer,
            "generator": generator,
        }
        logger.info("agent_invitro components initialized (provider=bedrock)")
        return _components


# ---------------------------------------------------------------------------
# search_knowledge 呼び出しと結果パース（T4）
# ---------------------------------------------------------------------------
def _extract_results(raw) -> list[dict]:
    """search_knowledge の戻り値から results 配列を頑健に取り出す（ADR-0063）。

    langchain-mcp-adapters のバージョン差で戻り値が「JSON 文字列」「(content, artifact)
    タプル」「dict」「テキストブロックの list」のいずれにもなり得るため、tags.py の
    _mcp_result_to_dicts で全形式を吸収したうえで results を取り出す。旧実装はテキスト
    ブロックの list を results として解釈できず、コンテンツブロックそのものを返して実質
    空コンテキストを生んでいた（ADR-0063 コンテキスト 3.2 節）。
    """
    payloads = _mcp_result_to_dicts(raw)
    for payload in payloads:
        results = payload.get("results")
        if isinstance(results, list):
            return results
    # 「results」キーを持つ dict が無い場合でも、要素自体が結果 dict の list（id/title/
    # content のいずれかを持つ）であればそれを結果とみなす（ラップなしで配列を返す版への保険）。
    if payloads and any(
        ("id" in d or "title" in d or "content" in d) for d in payloads
    ):
        return payloads
    logger.warning(
        "search_knowledge 応答から results を取り出せませんでした: type=%s head=%s",
        type(raw).__name__,
        repr(raw)[:300],
    )
    return []


async def _search_knowledge(search_tool, query: str, top_k: int = 3) -> list[dict]:
    """Knowledge MCP の search_knowledge ツールを1回呼び出し、結果 dict のリストを返す。

    T4: クエリ整形の明示的ステップは追加せず、query をそのまま検索クエリとして渡す。
    """
    raw = await search_tool.ainvoke({"query": query, "top_k": top_k})
    return _extract_results(raw)


def _build_context(results: list[dict]) -> str:
    """search_knowledge の結果からプロンプト用のコンテキスト文字列を構築する。

    search_knowledge の出力スキーマ（title=QA タイトル / content=回答本文）に沿って整形する。
    """
    return "\n".join(
        f"Q: {r.get('title', '')}\nA: {r.get('content', '')}" for r in results
    )


# ---------------------------------------------------------------------------
# 要約（web_backend の _summarize_oldest 相当, T3）
# ---------------------------------------------------------------------------
def _summarize_oldest(
    summarizer: SummarizeLLMBedrock,
    messages: list[Message],
    summary: Summary,
    n: int = 3,
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


# ---------------------------------------------------------------------------
# POST /ask-sl（T3）
# ---------------------------------------------------------------------------
@app.post("/ask-sl", response_model=Response)
async def ask(req: Request) -> Response:
    """/ask-sl エンドポイント。例外を握りつぶさず、スタックトレースをログ出力したうえで
    エラー種別・メッセージを 500 の detail に含めて返す（社内IP限定のため詳細開示は許容）。"""
    try:
        return await _ask_impl(req)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 予期しない例外は詳細をログ+レスポンスへ伝える
        logger.exception("POST /ask-sl failed")
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


async def _ask_impl(req: Request) -> Response:
    components = await _get_components()
    search_tool = components["search_tool"]
    tags_tool = components["tags_tool"]
    summarizer: SummarizeLLMBedrock = components["summarizer"]
    generator: GenerateAnswerLLMBedrock = components["generator"]
    settings = components["settings"]
    model_id = settings.bedrock_chat_model_id

    conversation_id = req.conversation_id or str(uuid.uuid4())
    messages = list(req.messages)
    summary = req.summary
    client_tags = req.tags or []

    # 15件以上のとき、order が若い順に 3 件を要約して messages から除外する（web_backend と同一）。
    if len(messages) >= 15:
        messages, summary = await run_in_threadpool(
            _summarize_oldest, summarizer, messages, summary
        )

    # 会話履歴と order を事前計算する。
    next_order = (max(m.order for m in messages) + 1) if messages else 1
    history = [
        {"role": m.role, "content": m.content}
        for m in sorted(messages, key=lambda m: m.order)
    ] or None

    ### ↓この辺をもう少しAgenticに？

    # --- select_tags 呼び出し（IMPL-202608261345 T9 / ADR-0057）---
    try:
        raw_tags = await tags_tool.ainvoke({
            "query": req.text,
            "max_tags": settings.tag_selector_max_tags,
            "confidence_threshold": settings.tag_selector_confidence_threshold,
        })
        new_tags = _extract_selected_tags(raw_tags)
    except Exception:
        logger.exception("select_tags failed")
        new_tags = []   # 失敗時は空集合として継続する（要件定義書6.4.1節）

    # --- 継続タグ判定（マージ）---
    conversation_tags = compute_conversation_tags(
        new_tags,
        client_tags,
        max_missed_turns=settings.tag_context_max_missed_turns,
        max_tags=settings.tag_context_max_tags,
    )

    # --- QA 類似検索（tags.py 経由、マージタグ全件を1回で渡す単一呼び出し, ADR-0062）---
    results = await search_with_merged_tags(
        search_tool,
        _extract_results,
        req.text,
        conversation_tags,
        top_k=3,
    )
    logger.info(
        "search_with_merged_tags query=%r merged_tags=%d hits=%d",
        req.text, len(conversation_tags), len(results),
    )
    context = _build_context(results)

    # ユーザーメッセージ追加（コンテキスト込み。web_backend の content 形式と同一）。
    user_msg = Message(
        order=next_order,
        role="user",
        content=f"参考情報:\n{context}\n\n質問:\n{req.text}",
    )
    messages.append(user_msg)

    # LLM 回答生成（Bedrock, T6）。boto3 は同期 API のためスレッドプールで実行する。
    answer, prompt = await run_in_threadpool(
        generator.generate,
        context,
        req.text,
        summary.content,
        history,
    )
    logger.info("bedrock generate model=%s answer_len=%d", model_id, len(answer))

    ### ↑この辺をもう少しAgenticに？

    assistant_msg = Message(
        order=next_order + 1,
        role="assistant",
        content=answer,
        input=prompt,
        model=model_id,
        evaluation=0,
    )
    messages.append(assistant_msg)

    return Response(
        conversation_id=conversation_id,
        messages=messages,
        summary=summary,
        tags=[
            ConversationTag(id=t.id, name=t.name, score=t.score, missed_turns=t.missed_turns)
            for t in conversation_tags
        ],
    )


# ---------------------------------------------------------------------------
# GET /health（ECS コンテナヘルスチェック専用, T2）
# ---------------------------------------------------------------------------
# プロセスが応答できることのみを 200 で返す。DB・MCP・Bedrock への到達性は確認しない
# （既存 knowledge_mcp / tag_selector_mcp と同方針、ADR-0043）。ALB 配下ではないため
# ALB ターゲットグループのヘルスチェックとは別物（10章）。
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
