"""シード投入用の DB アクセス（web_backend/src/db.py の exists_* / insert_* を移管）。

search_similar はチャット機能で使うため web_backend/src/db.py に残す（要件定義書10章）。
テーブル単位の存在チェックによる冪等性は現行方式をそのまま踏襲する（ADR-0018）。
"""

from typing import List

import psycopg2

from models import Category, QAOriginal, QuestionAltered


class DB:
    def __init__(self, url: str):
        self.url = url
        self.conn = psycopg2.connect(self.url)

    def exists_qa_original(self) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM qa_original);")
            return cur.fetchone()[0]

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
            cur.execute("SELECT EXISTS (SELECT 1 FROM category);")
            return cur.fetchone()[0]

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
            cur.execute("SELECT EXISTS (SELECT 1 FROM question_altered);")
            return cur.fetchone()[0]

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
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.close()
