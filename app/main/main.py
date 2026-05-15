from fastapi import FastAPI
from pydantic import BaseModel
import os

from src.embedding import get_embedding
from src.db import DB
from src.llm import generate_answer

app = FastAPI()


class Question(BaseModel):
    text: str

DATABASE_URL = os.environ["DATABASE_URL"]
LMSTUDIO_CHAT_URL = os.environ["LMSTUDIO_CHAT_URL"]
MODEL_CHAT = os.environ["MODEL_CHAT"]
EMBEDDING_URL = os.environ["LMSTUDIO_EMBEDDING_URL"]
EMBEDDING_MODEL=os.environ["MODEL_EMBEDDING"]

@app.post("/ask")
def ask(q: Question):
    # 1. embedding
    # emb = get_embedding(q.text)
    emb = get_embedding(
        EMBEDDING_URL, 
        EMBEDDING_MODEL, 
        q.text
    )

    # 2. 類似検索
    with DB(DATABASE_URL) as db: 
        results = db.search_similar(emb, 1)

    # 3. コンテキスト生成
    context = "\n".join(
        [f"Q: {r[0]}\nA: {r[1]}" for r in results]
    )

    # 4. LLM生成
    answer = generate_answer(
        LMSTUDIO_CHAT_URL,
        MODEL_CHAT,
        context, 
        q.text
    )

    return {"answer": answer}