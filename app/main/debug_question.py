from pydantic import BaseModel
import os
from datetime import datetime
from zoneinfo import ZoneInfo


from src.embedding import get_embedding
from src.db import DB
from src.llm import generate_answer

class Question(BaseModel):
    text: str

DATABASE_URL = os.environ["DATABASE_URL"]
LMSTUDIO_CHAT_URL = os.environ["LMSTUDIO_CHAT_URL"]
MODEL_CHAT = os.environ["MODEL_CHAT"]
EMBEDDING_URL = os.environ["LMSTUDIO_EMBEDDING_URL"]
EMBEDDING_MODEL=os.environ["MODEL_EMBEDDING"]


def main():

    question:str = "マスタにない歩掛を独自で作成するにはどうすればいいですか？"
    print(datetime.now(ZoneInfo("Asia/Tokyo")))
    print(f"====== Question:\n{question}\n\n")
    # 1. embedding
    emb = get_embedding(
        EMBEDDING_URL, 
        EMBEDDING_MODEL, 
        question
    )

    # 2. 類似検索
    with DB(DATABASE_URL) as db:
        results = db.search_similar(emb, 1)

    # 3. コンテキスト生成
    context = "\n".join(
        [f"Q_similar: {r[0]}\nQ_original: {r[2]}\nA_original: {r[1]}\nDistance: {r[4]}" for r in results]
    )
    print(datetime.now(ZoneInfo("Asia/Tokyo")))
    print(f"====== Similar:\n{context}\n\n")

    # 4. LLM生成
    answer = generate_answer(
        LMSTUDIO_CHAT_URL,
        MODEL_CHAT,
        context, 
        question
    )
    print(datetime.now(ZoneInfo("Asia/Tokyo")))
    print(f"====== Answer:\n{answer}\n\n")
    return {"answer": answer}


if __name__ == "__main__":
    main()