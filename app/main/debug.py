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

    with DB(DATABASE_URL) as db:
        result = db.exists_category()
        print(result)



if __name__ == "__main__":
    main()