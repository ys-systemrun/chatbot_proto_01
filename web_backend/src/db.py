import psycopg2


class DB:
    def __init__(
        self,
        url: str,
    ):
        self.url = url
        self.conn = psycopg2.connect(self.url)

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


def to_vector_str(vec):
    return "[" + ",".join(map(str, vec)) + "]"
