from __future__ import annotations

import json
import uuid

import psycopg2

from .models import (
    EvaluatedConversationData,
    EvaluatedMessageData,
    MessageRecord,
    ReleaseData,
)

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
        m.created_at,
        m.release_id,
        m.ask_mode,
        m.evaluation_comment,
        m.evaluated_at,
        r.git_commit,
        r.git_dirty,
        r.prompt_hash,
        r.chat_model_id,
        r.embedding_model_id,
        r.params,
        r.first_seen_at
    FROM conversation c
    LEFT JOIN message m ON m.conversation_id = c.id
    LEFT JOIN release r ON r.release_id = m.release_id
    ORDER BY c.created_at DESC, m."order" ASC
"""


def _iso(value) -> str | None:
    return value.isoformat() if value else None


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
            - 存在すれば evaluation と evaluation_comment のみ UPDATE。どちらかが変わったときだけ
              evaluated_at を現在時刻にする（ADR-0099 §4）
        """
        self._upsert_conversation(conversation_id)
        for msg in messages:
            self._upsert_message(conversation_id, msg)

    def has_release(self, release_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("SELECT 1 FROM release WHERE release_id = %s", (release_id,))
            return cur.fetchone() is not None

    def register_release(self, release: dict) -> None:
        """リリース（agent_invitro の GET /release の内容）を登録する。登録済みなら何もしない。"""
        sql = """
            INSERT INTO release (
                release_id, git_commit, git_dirty, prompt_hash,
                chat_model_id, embedding_model_id, params, first_seen_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (release_id) DO NOTHING
        """
        params = release.get("params")
        with self._conn.cursor() as cur:
            cur.execute(sql, (
                release["release_id"],
                release.get("git_commit"),
                release.get("git_dirty"),
                release.get("prompt_hash"),
                release.get("chat_model_id"),
                release.get("embedding_model_id"),
                json.dumps(params, ensure_ascii=False, sort_keys=True) if params is not None else None,
            ))

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
                release_id = row[10]
                release = None
                # release テーブルに未登録（回答時の登録に失敗した等）なら ID だけを返す。
                if release_id is not None and row[20] is not None:
                    release = ReleaseData(
                        release_id=release_id,
                        git_commit=row[14],
                        git_dirty=row[15],
                        prompt_hash=row[16],
                        chat_model_id=row[17],
                        embedding_model_id=row[18],
                        params=json.loads(row[19]) if row[19] else None,
                        first_seen_at=_iso(row[20]),
                    )
                conversations[conv_id].messages.append(EvaluatedMessageData(
                    id=row[2],
                    order=row[3],
                    role=row[4],
                    evaluation=row[5],
                    input=row[6],
                    model=row[7],
                    content=row[8],
                    created_at=row[9].isoformat() if row[9] else "",
                    release_id=release_id,
                    ask_mode=row[11],
                    evaluation_comment=row[12],
                    evaluated_at=_iso(row[13]),
                    release=release,
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
        # evaluated_at: INSERT 時は評価（1/2）か理由があれば現在時刻。UPDATE 時は評価・理由が
        # 変わったときだけ現在時刻にする（会話全体を送り直しても他メッセージの日時は動かない）。
        sql = """
            INSERT INTO message (
                id, conversation_id, "order", role, evaluation, input, model, content, created_at,
                release_id, ask_mode, evaluation_comment, evaluated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, NOW(),
                %s, %s, %s,
                CASE WHEN %s IN (1, 2) OR %s IS NOT NULL THEN NOW() END
            )
            ON CONFLICT (conversation_id, "order")
            DO UPDATE SET
                evaluation = EXCLUDED.evaluation,
                evaluation_comment = EXCLUDED.evaluation_comment,
                evaluated_at = CASE
                    WHEN message.evaluation IS DISTINCT FROM EXCLUDED.evaluation
                      OR message.evaluation_comment IS DISTINCT FROM EXCLUDED.evaluation_comment
                    THEN NOW()
                    ELSE message.evaluated_at
                END
        """
        comment = (msg.evaluation_comment or "").strip() or None
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
                msg.release_id,
                msg.ask_mode,
                comment,
                msg.evaluation,
                comment,
            ))
