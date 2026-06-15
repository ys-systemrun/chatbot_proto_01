import uuid

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import os

from src.embedding import get_embedding
from src.db import DB
from src.llm import generate_answer_stateful
from src.models.conversation_state import ConversationState
from src.session import InMemorySessionStore

app = FastAPI()

DATABASE_URL = os.environ["DATABASE_URL"]
LMSTUDIO_CHAT_URL = os.environ["LMSTUDIO_CHAT_URL"]
MODEL_CHAT = os.environ["MODEL_CHAT"]
EMBEDDING_URL = os.environ["LMSTUDIO_EMBEDDING_URL"]
EMBEDDING_MODEL = os.environ["MODEL_EMBEDDING"]

_SYSTEM_PROMPT = """\
あなたは当社製品専門の優秀なカスタマーサポートAIです。
顧客からのトラブルや操作方法に関する質問に対し、参考情報をもとにルールに沿って解決策を提案してください。

応答のルール:
1. まずは「お問い合わせいただきありがとうございます」と挨拶してください。
2. 参考情報に回答に必要な情報が含まれる場合は、解決策はステップ・バイ・ステップで手順を分けて提示し、回答の最後には「こちらの方法で解決しない場合は、お手数ですが有人サポートまでご連絡ください」と添えてください。
3. 問い合わせ内容があいまいで参考情報に回答に必要な情報が得られなかった場合は、「申し訳ございません、ご提供いただいた情報が不足しています。より詳しい情報を入力してください。」と回答してください。
4. 問い合わせ内容が当社製品と関係がない場合は、「申し訳ございません、当社の製品に関する操作方法やトラブルシューティングの範疇を超えるため、現在お手持ちの情報からはお答えすることができませんでした。」と回答してください。
"""

# セッションストア（実装の差し替えはここだけ）
# - 開発・単一プロセス: InMemorySessionStore()
# - ファイル永続化:    FileSessionStore("sessions/")
# - Redis 分散:        RedisSessionStore(os.environ["REDIS_URL"])
# store = InMemorySessionStore()

# class Message(BaseModel):
#     order: int # summary_message の order は 0 とする？
#     role: str
#     content: str
#     summary_message: bool

# class Request(BaseModel):
#     session_id: str | None = None  # None の場合はサーバー側で新規発行
#     text: str
#     messages: list[Message]


# class Response(BaseModel):
#     session_id: str
#     messages: list[Message]

# @app.post("/ask", response_model=Response)
    


# def _build_user_content(context: str, question: str) -> str:
#     return f"参考情報:\n{context}\n\n質問:\n{question}"


# @app.post("/ask", response_model=Answer)
# def ask(q: Question):
#     # セッション解決
#     session_id = q.session_id or str(uuid.uuid4())

#     state = store.get(session_id)
#     if state is None:
#         state = ConversationState()
#         state.append_message("system", _SYSTEM_PROMPT)

#     # 1. embedding
#     emb = get_embedding(EMBEDDING_URL, EMBEDDING_MODEL, q.text)

#     # 2. 類似検索
#     with DB(DATABASE_URL) as db:
#         results = db.search_similar(emb, 3)

#     # 3. コンテキスト生成
#     context = "\n".join(
#         f"Q_similar: {r[0]}\nQ_original: {r[2]}\nA_original: {r[1]}" for r in results
#     )

#     # 4. メッセージ追加 → LLM 生成
#     state.append_message("user", _build_user_content(context, q.text))

#     answer = generate_answer_stateful(
#         LMSTUDIO_CHAT_URL,
#         MODEL_CHAT,
#         state.messages_as_dicts(),
#     )

#     state.append_message("assistant", answer)

#     # 5. セッション保存
#     store.save(session_id, state)

#     return Answer(session_id=session_id, answer=answer)


# @app.delete("/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
# def delete_session(session_id: str):
#     """セッションを明示的に削除する。"""
#     store.delete(session_id)
