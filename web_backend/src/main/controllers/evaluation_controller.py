"""/evaluate_response・/evaluated_messages のレスポンス生成ロジック。

旧 main/main_stateless.py の評価登録・評価済み一覧ハンドラ本体とスキーマを移設したもの。
"""

from pydantic import BaseModel

from src.conversation_db import (
    ConversationDB,
    EvaluatedConversationData,
    MessageRecord,
)
from src.main import config

_ROLE_TO_INT = {"user": 1, "assistant": 2}


# --- /evaluate_response ---------------------------------------------------- #
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


# --- /evaluated_messages --------------------------------------------------- #
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


def evaluate_response(req: EvaluateRequest) -> EvaluateResponse:
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
    with ConversationDB(config.CONVERSATION_DB_URL) as db:
        db.upsert(req.conversation_id, records)
    return EvaluateResponse(conversation_id=req.conversation_id)


def get_evaluated_messages() -> list[EvaluatedConversationOut]:
    with ConversationDB(config.CONVERSATION_DB_URL) as db:
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
