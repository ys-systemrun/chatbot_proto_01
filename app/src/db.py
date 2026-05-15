import psycopg2
import uuid

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
        """
        embedding: 埋め込みベクトル
        """
        with self.conn.cursor() as cur:
            cur = self.conn.cursor()

            vec_str = to_vector_str(embedding)

            cur.execute(
                """
                SELECT question, answer
                FROM qa
                ORDER BY embedding <-> %s
                LIMIT %s
                """,
                (vec_str, top_k)
            )
            results = cur.fetchall()
            return results
        
    def exist_any(self) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM qa
                );
                """,
            )
            results = cur.fetchone()[0]
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


