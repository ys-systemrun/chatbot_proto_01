from __future__ import annotations

import uuid

import psycopg2

from .models import EvaluatedConversationData, EvaluatedMessageData, MessageRecord

_SELECT_ALL_SQL = """
    SELECT
        c.id,
        c.created_at,
        m.id,
        m."order",
        m.role,
        m.evaluation,
        m.input,
        m.model,
        m.content,
        m.created_at
    FROM conversation c
    LEFT JOIN message m ON m.conversation_id = c.id
    ORDER BY c.created_at DESC, m."order" ASC
"""


class ConversationDB:
    """会話・メッセージの upsert / 取得を行うコンテキストマネージャー。"""

    def __init__(self, url: str) -> None:
        self._url = url
        self._conn = None

    def __enter__(self) -> ConversationDB:
        self._conn = psycopg2.connect(self._url)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._conn:
            if exc_type:
                self._conn.rollback()
            else:
                self._conn.commit()
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def upsert(self, conversation_id: str, messages: list[MessageRecord]) -> None:
        """conversation と message を upsert する。

        - conversation が存在しなければ INSERT。
        - message は (conversation_id, order) をキーとして:
            - 存在しなければ INSERT
            - 存在すれば evaluation のみ UPDATE
        """
        self._upsert_conversation(conversation_id)
        for msg in messages:
            self._upsert_message(conversation_id, msg)

    def get_all_conversations(self) -> list[EvaluatedConversationData]:
        """全 conversation とその message 一覧を返す（新しい順）。"""
        with self._conn.cursor() as cur:
            cur.execute(_SELECT_ALL_SQL)
            rows = cur.fetchall()

        conversations: dict[str, EvaluatedConversationData] = {}
        for row in rows:
            conv_id = row[0]
            if conv_id not in conversations:
                conversations[conv_id] = EvaluatedConversationData(
                    id=conv_id,
                    created_at=row[1].isoformat() if row[1] else "",
                )
            if row[2] is not None:  # message.id
                conversations[conv_id].messages.append(EvaluatedMessageData(
                    id=row[2],
                    order=row[3],
                    role=row[4],
                    evaluation=row[5],
                    input=row[6],
                    model=row[7],
                    content=row[8],
                    created_at=row[9].isoformat() if row[9] else "",
                ))

        return list(conversations.values())

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    def _upsert_conversation(self, conversation_id: str) -> None:
        sql = """
            INSERT INTO conversation (id, created_at)
            VALUES (%s, NOW())
            ON CONFLICT (id) DO NOTHING
        """
        with self._conn.cursor() as cur:
            cur.execute(sql, (conversation_id,))

    def _upsert_message(self, conversation_id: str, msg: MessageRecord) -> None:
        sql = """
            INSERT INTO message (id, conversation_id, "order", role, evaluation, input, model, content, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (conversation_id, "order")
            DO UPDATE SET evaluation = EXCLUDED.evaluation
        """
        with self._conn.cursor() as cur:
            cur.execute(sql, (
                str(uuid.uuid4()),
                conversation_id,
                msg.order,
                msg.role,
                msg.evaluation,
                msg.input,
                msg.model,
                msg.content,
            ))
