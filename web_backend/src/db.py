from typing import List

import psycopg2
import uuid

from .models.category import Category
from .models.qa_original import QAOriginal
from .models.question_altered import QuestionAltered



class DB:
    def __init__(
        self,
        url: str,
    ):
        self.url = url
        self.conn = psycopg2.connect(self.url)

        # psycopg2.connect(os.environ["DATABASE_URL"])

        # self.cursor = self.conn.cursor(
        #     cursor_factory=RealDictCursor
        # )

    # def execute(self, sql: str, params=None):
    #     self.cursor.execute(sql, params)

    # def fetchone(self):
    #     return self.cursor.fetchone()

    # def fetchall(self):
    #     return self.cursor.fetchall()

    # def commit(self):
    #     self.conn.commit()

    # def rollback(self):
    #     self.conn.rollback()

    def search_similar(self, embedding, top_k=3):
        with self.conn.cursor() as cur:
            cur = self.conn.cursor()

            vec_str = to_vector_str(embedding)
            # question_altered (id, qa_id, text, embedding)
            cur.execute(
                """
                SELECT 
                    question_altered.text as question, 
                    qa_original.answer_text as answer,
                    qa_original.question_text as question_original,
                    question_altered.qa_id as qa_id,
                    embedding <=> %s as distance
                FROM question_altered
                LEFT JOIN qa_original ON question_altered.qa_id = qa_original.uuid
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (vec_str, vec_str, top_k)
            )
            results = cur.fetchall()
            return results


    def insert_qa(self, question, answer, embedding, rec_uuid=""):
        rec_id = uuid.uuid4() if rec_uuid=="" else rec_uuid
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO qa (uuid, question, answer, embedding)
                VALUES (%s, %s, %s, %s)
                """,
                (str(rec_id), question, answer, embedding)
            )
    
    def exists_qa_original(self) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM qa_original
                );
                """,
            )
            results = cur.fetchone()[0]
            return results

    def insert_qa_original(self, rows: List[QAOriginal]):
        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO qa_original (uuid, question_text, answer_text, category_id)
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (row.uuid, row.question_text, row.answer_text, row.category_id)
                    for row in rows
                ],
            )
    

    def exists_category(self) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM category
                );
                """,
            )
            results = cur.fetchone()[0]
            return results

    def insert_category(self, rows: List[Category]):
        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO category (id, name)
                VALUES (%s, %s)
                """,
                [(row.id, row.name) for row in rows],
            )
    
    def exists_question_altered(self) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM question_altered
                );
                """,
            )
            results = cur.fetchone()[0]
            return results
    
    def insert_question_altered(self, rows: List[QuestionAltered]):
        with self.conn.cursor() as cur:
            values = [row.to_tuple() for row in rows]
            if values and len(values[0]) == 4:
                cur.executemany(
                    """
                    INSERT INTO question_altered (id, qa_id, text, embedding)
                    VALUES (%s, %s, %s, %s)
                    """,
                    values,
                )
            else:
                cur.executemany(
                    """
                    INSERT INTO question_altered (qa_id, text, embedding)
                    VALUES (%s, %s, %s)
                    """,
                    values,
                )



    def close(self):
        # if self.cursor:
        #     self.cursor.close()

        if self.conn:
            self.conn.close()

    def __enter__(self):
        # self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()

        self.close()

# def get_conn():
#     return psycopg2.connect(os.environ["DATABASE_URL"])

def to_vector_str(vec):
    return "[" + ",".join(map(str, vec)) + "]"


