import uuid

from fastapi import FastAPI
from pydantic import BaseModel
import os

from src.embedding import get_embedding
from src.db import DB
from src.conversation_db import ConversationDB, EvaluatedConversationData, MessageRecord
from src.llm import FormatQueryToEmbed, GenerateAnswerLLM, SummarizeLLM
from src.log import log_format_query, log_generate, log_search
from src.models.stateless.message import Message as ModelMessage

app = FastAPI()

DATABASE_URL = os.environ["DATABASE_URL"]
CONVERSATION_DB_URL = os.environ["CONVERSATION_DB_URL"]
LMSTUDIO_CHAT_URL = os.environ["LMSTUDIO_CHAT_URL"]
MODEL_CHAT = os.environ["MODEL_CHAT"]
EMBEDDING_URL = os.environ["LMSTUDIO_EMBEDDING_URL"]
EMBEDDING_MODEL = os.environ["MODEL_EMBEDDING"]

_summarizer = SummarizeLLM(LMSTUDIO_CHAT_URL, MODEL_CHAT)
_query_formatter = FormatQueryToEmbed(LMSTUDIO_CHAT_URL, MODEL_CHAT)
_generator = GenerateAnswerLLM(LMSTUDIO_CHAT_URL, MODEL_CHAT)


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


class Request(BaseModel):
    conversation_id: str | None = None  # None の場合はサーバー側で新規発行
    text: str
    messages: list[Message]
    summary: Summary


class Response(BaseModel):
    conversation_id: str
    messages: list[Message]
    summary: Summary


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

    # combined = (
    #     f"{summary.content}\n{new_text}".strip() if summary.content else new_text
    # )

    return rest, Summary(
        content=new_text,
        summarized_upto=to_summarize[-1].order,
    )


@app.post("/ask-sl", response_model=Response)
def ask(req: Request):
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
    log_format_query(format_input, formatted_query, MODEL_CHAT)

    # 3. embedding
    emb = get_embedding(EMBEDDING_URL, EMBEDDING_MODEL, formatted_query)

    # 4. 類似検索
    with DB(DATABASE_URL) as db:
        results = db.search_similar(emb, 3)
    log_search(formatted_query, results, EMBEDDING_MODEL)

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
    log_generate(prompt, answer, MODEL_CHAT)

    # 8. アシスタントメッセージ追加
    assistant_msg = Message(
        order=next_order + 1,
        role="assistant",
        content=answer,
        input=prompt,
        model=MODEL_CHAT,
        evaluation=0,
    )
    messages.append(assistant_msg)

    return Response(
        conversation_id=conversation_id,
        messages=messages,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# /evaluate_response
# ---------------------------------------------------------------------------

_ROLE_TO_INT = {"user": 1, "assistant": 2}


class EvaluateMessage(BaseModel):
    order: int
    role: str                   # "user" | "assistant"
    content: str | None = None
    evaluation: int | None = None
    input: str | None = None    # assistant メッセージ生成時の LLM 入力
    model: str | None = None    # assistant メッセージ生成に使ったモデル名


class EvaluateRequest(BaseModel):
    conversation_id: str
    messages: list[EvaluateMessage]


class EvaluateResponse(BaseModel):
    conversation_id: str


@app.post("/evaluate_response", response_model=EvaluateResponse)
def evaluate_response(req: EvaluateRequest):
    records = [
        MessageRecord(
            order=m.order,
            role=_ROLE_TO_INT[m.role],
            evaluation=m.evaluation,
            input=m.input,
            model=m.model,
            content=m.content,
        )
        for m in req.messages
    ]
    with ConversationDB(CONVERSATION_DB_URL) as db:
        db.upsert(req.conversation_id, records)
    return EvaluateResponse(conversation_id=req.conversation_id)


# ---------------------------------------------------------------------------
# /evaluated_messages
# ---------------------------------------------------------------------------

class EvaluatedMessageOut(BaseModel):
    id: str
    order: int
    role: int
    evaluation: int | None
    input: str | None
    model: str | None
    content: str | None
    created_at: str


class EvaluatedConversationOut(BaseModel):
    id: str
    created_at: str
    messages: list[EvaluatedMessageOut]


@app.get("/evaluated_messages", response_model=list[EvaluatedConversationOut])
def get_evaluated_messages():
    with ConversationDB(CONVERSATION_DB_URL) as db:
        conversations: list[EvaluatedConversationData] = db.get_all_conversations()
    return [
        EvaluatedConversationOut(
            id=c.id,
            created_at=c.created_at,
            messages=[
                EvaluatedMessageOut(
                    id=m.id,
                    order=m.order,
                    role=m.role,
                    evaluation=m.evaluation,
                    input=m.input,
                    model=m.model,
                    content=m.content,
                    created_at=m.created_at,
                )
                for m in c.messages
            ],
        )
        for c in conversations
    ]
