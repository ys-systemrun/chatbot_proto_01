"""/ask-sl のレスポンス生成ロジック（stateless 会話）。

旧 main/main_stateless.py の /ask-sl ハンドラ本体・関連スキーマ・LLM シングルトンを移設したもの。
ルート定義（app.py）からは ask() を呼び出すだけにし、応答生成の責務を本 Controller に集約する。
"""

import uuid

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

from src.embedding import get_embedding
from src.db import DB
from src.llm import FormatQueryToEmbed, GenerateAnswerLLM, SummarizeLLM
from src.log import log_format_query, log_generate, log_search
from src.models.stateless.message import Message as ModelMessage
from src.main import config


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
    tags: list[ConversationTag] | None = None   # 会話タグ（IMPL-202608261345 T4 / ADR-0056）


class Response(BaseModel):
    conversation_id: str
    messages: list[Message]
    summary: Summary
    tags: list[ConversationTag] | None = None   # 会話タグ（IMPL-202608261345 T4 / ADR-0056）


_summarizer = SummarizeLLM(config.LMSTUDIO_CHAT_URL, config.MODEL_CHAT)
_query_formatter = FormatQueryToEmbed(config.LMSTUDIO_CHAT_URL, config.MODEL_CHAT)
_generator = GenerateAnswerLLM(config.LMSTUDIO_CHAT_URL, config.MODEL_CHAT)


def _summarize_oldest(
    messages: list[Message],
    summary: Summary,
    n: int = 3,
) -> tuple[list[Message], Summary]:
    """order の昇順で先頭 n 件を要約し、残りメッセージと更新後の Summary を返す。

    既存の summary.content がある場合は新しい要約テキストを末尾に追記する。
    """
    sorted_msgs = sorted(messages, key=lambda m: m.order)
    to_summarize = sorted_msgs[:n]
    rest = sorted_msgs[n:]

    msgs = [ModelMessage(m.order, m.role, m.content) for m in to_summarize]
    new_text = _summarizer.summarize(msgs, summary.content)

    return rest, Summary(
        content=new_text,
        summarized_upto=to_summarize[-1].order,
    )


def ask(req: Request) -> Response:
    # AWS 環境（AGENT_INVITRO_URL 設定時, ADR-0045）: リクエストをそのまま agent_invitro へ
    # 中継し、レスポンスをそのまま返す。ローカル docker-compose（未設定時）は分岐に入らず、
    # 下の既存の直接処理ロジック（LM Studio 経由）をそのまま実行する（T11/T13）。
    if config.AGENT_INVITRO_URL:
        try:
            resp = httpx.post(
                f"{config.AGENT_INVITRO_URL}/ask-sl",
                json=req.model_dump(),
                timeout=config.AGENT_INVITRO_TIMEOUT,
            )
        except httpx.RequestError as exc:
            # 接続不可・タイムアウト等（agent_invitro 未起動/到達不可）。502 で明示する。
            raise HTTPException(
                status_code=502,
                detail=f"agent_invitro への接続に失敗しました: {exc}",
            )
        # agent_invitro 側のエラー（500 等）を bare 500 で握りつぶさず、ステータスと
        # detail（{"detail": ...} 形式想定）をそのまま透過してブラウザ/ログに原因を残す。
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise HTTPException(status_code=resp.status_code, detail=detail)
        return Response(**resp.json())

    conversation_id = req.conversation_id or str(uuid.uuid4())
    messages = list(req.messages)
    summary = req.summary

    # 15件以上のとき、order が若い順に 3 件を要約して messages から除外する
    if len(messages) >= 15:
        messages, summary = _summarize_oldest(messages, summary)

    # 1. 会話履歴と order を事前計算（クエリ整形・LLM 生成で共通利用）
    next_order = (max(m.order for m in messages) + 1) if messages else 1
    history = [
        {"role": m.role, "content": m.content}
        for m in sorted(messages, key=lambda m: m.order)
    ] or None

    # 2. 類似検索用クエリの整形
    formatted_query, format_input = _query_formatter.format(
        req.text,
        summary=summary.content,
        history=history,
    )
    log_format_query(format_input, formatted_query, config.MODEL_CHAT)

    # 3. embedding
    emb = get_embedding(config.EMBEDDING_URL, config.EMBEDDING_MODEL, formatted_query)

    # 4. 類似検索
    with DB(config.DATABASE_URL) as db:
        results = db.search_similar(emb, 3)
    log_search(formatted_query, results, config.EMBEDDING_MODEL)

    # 5. コンテキスト生成
    context = "\n".join(
        f"Q_similar: {r[0]}\nQ_original: {r[2]}\nA_original: {r[1]}" for r in results
    )

    # 6. ユーザーメッセージ追加（コンテキスト込み）
    user_msg = Message(
        order=next_order,
        role="user",
        content=f"参考情報:\n{context}\n\n質問:\n{req.text}",
    )
    messages.append(user_msg)

    # 7. LLM 回答生成
    answer, prompt = _generator.generate(
        context,
        req.text,
        summary=summary.content,
        history=history,
    )
    log_generate(prompt, answer, config.MODEL_CHAT)

    # 8. アシスタントメッセージ追加
    assistant_msg = Message(
        order=next_order + 1,
        role="assistant",
        content=answer,
        input=prompt,
        model=config.MODEL_CHAT,
        evaluation=0,
    )
    messages.append(assistant_msg)

    return Response(
        conversation_id=conversation_id,
        messages=messages,
        summary=summary,
    )
