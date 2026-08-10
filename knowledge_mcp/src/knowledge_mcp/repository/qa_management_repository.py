"""QaManagementRepository（実装指示書 4.1 / T1 / ADR-0014）。

qa_original / question_altered / qa_tag への CRUD と、question_text の embedding 計算を提供する。
既存 QARepository（ベクトル類似検索）とは別に、管理UI向けの単純な条件検索・登録・編集を担う。

**内部状態としてQA・タグ情報をキャッシュしないこと**（ADR-0006の設計方針を踏襲。都度DB参照）。
"""

from __future__ import annotations

import uuid
from typing import Callable, List, Optional, Tuple

from ..db.connection import Database, to_vector_str
from ..models.qa import QaDetail, QaError, QaSummary


class QaManagementRepository:
    def __init__(self, db: Database, embed_fn: Callable[[str], List[float]]):
        """
        db: DB接続ファクトリ（都度コネクションを生成する）。
        embed_fn: question_text をベクトル化する関数（DI、既存 embedding 呼び出しと同等）。
        """
        self.db = db
        self.embed_fn = embed_fn

    # ------------------------------------------------------------------ #
    # 参照系
    # ------------------------------------------------------------------ #
    def list_qa(
        self,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        tag_ids: Optional[List[int]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[QaSummary], int]:
        """(件数分のQaSummary, 絞り込み後の全体件数) を返す。

        ベクトル類似検索は行わず、keyword(部分一致)/category(名称完全一致)/tag_ids(AND)による
        単純な条件検索を行う（実装指示書10章）。
        """
        conditions: List[str] = []
        params: List = []

        if keyword:
            conditions.append(
                "(qa_original.title ILIKE %s"
                " OR qa_original.question_text ILIKE %s"
                " OR qa_original.answer_text ILIKE %s)"
            )
            like = f"%{keyword}%"
            params.extend([like, like, like])

        if category:
            conditions.append(
                "qa_original.category_id = (SELECT id FROM category WHERE name = %s)"
            )
            params.append(category)

        if tag_ids:
            # 指定タグIDをすべて持つQAのみに絞り込む（AND条件・完全一致）。
            conditions.append(
                """(
                    SELECT COUNT(DISTINCT qt.tag_id)
                    FROM qa_tag qt
                    WHERE qt.qa_id = qa_original.uuid
                      AND qt.tag_id = ANY(%s)
                ) = %s"""
            )
            params.append(list(tag_ids))
            params.append(len(set(tag_ids)))

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        count_sql = f"SELECT COUNT(*) FROM qa_original {where_clause}"

        list_sql = f"""
            SELECT
                qa_original.uuid AS qa_id,
                qa_original.title AS title,
                category.name AS category_name,
                COALESCE(
                    (
                        SELECT array_agg(tag.name ORDER BY tag.name)
                        FROM qa_tag
                        JOIN tag ON tag.id = qa_tag.tag_id
                        WHERE qa_tag.qa_id = qa_original.uuid
                    ),
                    ARRAY[]::text[]
                ) AS tags,
                (
                    SELECT COUNT(*)
                    FROM question_altered
                    WHERE question_altered.qa_id = qa_original.uuid
                ) AS question_altered_count
            FROM qa_original
            LEFT JOIN category ON qa_original.category_id = category.id
            {where_clause}
            ORDER BY qa_original.title NULLS LAST, qa_original.uuid
            LIMIT %s OFFSET %s
        """

        with self.db.cursor() as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()[0]

            cur.execute(list_sql, params + [limit, offset])
            rows = cur.fetchall()

        summaries = [
            QaSummary(
                id=row[0],
                title=row[1] or "",
                category=row[2],
                tags=list(row[3]) if row[3] else [],
                question_altered_count=row[4],
            )
            for row in rows
        ]
        return summaries, total

    def get_qa(self, qa_id: str) -> QaDetail:
        """存在しない場合はQaErrorを送出する。"""
        with self.db.cursor() as cur:
            detail = self._load_detail(cur, qa_id)
        if detail is None:
            raise QaError(f"qa id={qa_id} does not exist")
        return detail

    def list_categories(self) -> List[dict]:
        """[{"id": int, "name": str}, ...] を返す（category テーブルの単純SELECT）。"""
        with self.db.cursor() as cur:
            cur.execute("SELECT id, name FROM category ORDER BY id")
            rows = cur.fetchall()
        return [{"id": r[0], "name": r[1]} for r in rows]

    # ------------------------------------------------------------------ #
    # 更新系
    # ------------------------------------------------------------------ #
    def create_qa(
        self,
        title: str,
        question_text: str,
        answer_text: str,
        category_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
    ) -> QaDetail:
        if not title:
            raise QaError("title is required")
        if not question_text:
            raise QaError("question_text is required")
        if not answer_text:
            raise QaError("answer_text is required")

        # embedding はネットワーク呼び出しのためトランザクション外で先に計算する。
        embedding = self.embed_fn(question_text)
        vec_str = to_vector_str(embedding)

        qa_id = str(uuid.uuid4())
        with self.db.cursor() as cur:
            self._assert_category_exists(cur, category_id)
            self._assert_tags_exist(cur, tag_ids)

            cur.execute(
                """
                INSERT INTO qa_original (uuid, question_text, answer_text, category_id, title)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (qa_id, question_text, answer_text, category_id, title),
            )
            # 主となる質問文行（is_primary=true）を1件生成する。
            cur.execute(
                """
                INSERT INTO question_altered (qa_id, text, embedding, is_primary)
                VALUES (%s, %s, %s, true)
                """,
                (qa_id, question_text, vec_str),
            )
            if tag_ids:
                cur.executemany(
                    "INSERT INTO qa_tag (qa_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    [(qa_id, tid) for tid in tag_ids],
                )
            detail = self._load_detail(cur, qa_id)
        return detail

    def update_qa(
        self,
        qa_id: str,
        title: Optional[str] = None,
        question_text: Optional[str] = None,
        answer_text: Optional[str] = None,
        category_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
    ) -> QaDetail:
        """指定されたフィールドのみ更新する。

        - None は「変更なし」を意味する。
        - tag_ids は空リスト [] で「全解除」、None で「変更なし」を区別する。
        - question_text が指定された場合、is_primary=true の question_altered 行のみを再計算する。
        """
        # question_text 変更時は先に embedding を計算（トランザクション外）。
        vec_str = None
        if question_text is not None:
            if not question_text:
                raise QaError("question_text must not be empty")
            vec_str = to_vector_str(self.embed_fn(question_text))

        with self.db.cursor() as cur:
            if self._load_detail(cur, qa_id) is None:
                raise QaError(f"qa id={qa_id} does not exist")

            if category_id is not None:
                self._assert_category_exists(cur, category_id)
            if tag_ids is not None:
                self._assert_tags_exist(cur, tag_ids)

            # qa_original の部分更新（指定フィールドのみ）
            set_clauses: List[str] = []
            set_params: List = []
            if title is not None:
                set_clauses.append("title = %s")
                set_params.append(title)
            if question_text is not None:
                set_clauses.append("question_text = %s")
                set_params.append(question_text)
            if answer_text is not None:
                set_clauses.append("answer_text = %s")
                set_params.append(answer_text)
            if category_id is not None:
                set_clauses.append("category_id = %s")
                set_params.append(category_id)
            if set_clauses:
                cur.execute(
                    f"UPDATE qa_original SET {', '.join(set_clauses)} WHERE uuid = %s",
                    set_params + [qa_id],
                )

            # question_text 変更時: is_primary=true の1件のみ text/embedding を再計算。
            if question_text is not None:
                cur.execute(
                    """
                    UPDATE question_altered
                    SET text = %s, embedding = %s
                    WHERE qa_id = %s AND is_primary = true
                    """,
                    (question_text, vec_str, qa_id),
                )
                # 既存QA（is_primary行が無い旧データ）を編集した場合は、主行を新規作成する。
                # 既存パラフレーズ行（is_primary=false）は触らないため消失しない。
                if cur.rowcount == 0:
                    cur.execute(
                        """
                        INSERT INTO question_altered (qa_id, text, embedding, is_primary)
                        VALUES (%s, %s, %s, true)
                        """,
                        (qa_id, question_text, vec_str),
                    )

            # tag_ids 指定時: qa_tag を指定集合で置き換える（None は変更なし、[] は全解除）。
            if tag_ids is not None:
                cur.execute("DELETE FROM qa_tag WHERE qa_id = %s", (qa_id,))
                if tag_ids:
                    cur.executemany(
                        "INSERT INTO qa_tag (qa_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        [(qa_id, tid) for tid in tag_ids],
                    )

            detail = self._load_detail(cur, qa_id)
        return detail

    # ------------------------------------------------------------------ #
    # 内部ヘルパ
    # ------------------------------------------------------------------ #
    def _load_detail(self, cur, qa_id: str) -> Optional[QaDetail]:
        cur.execute(
            """
            SELECT
                qa_original.uuid,
                qa_original.title,
                qa_original.question_text,
                qa_original.answer_text,
                category.id,
                category.name
            FROM qa_original
            LEFT JOIN category ON qa_original.category_id = category.id
            WHERE qa_original.uuid = %s
            """,
            (qa_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None

        cur.execute(
            """
            SELECT tag.id, tag.name
            FROM qa_tag
            JOIN tag ON tag.id = qa_tag.tag_id
            WHERE qa_tag.qa_id = %s
            ORDER BY tag.name
            """,
            (qa_id,),
        )
        tags = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]

        cur.execute(
            "SELECT COUNT(*) FROM question_altered WHERE qa_id = %s", (qa_id,)
        )
        altered_count = cur.fetchone()[0]

        category = None
        if row[4] is not None:
            category = {"id": row[4], "name": row[5]}

        return QaDetail(
            id=row[0],
            title=row[1] or "",
            question_text=row[2] or "",
            answer_text=row[3] or "",
            category=category,
            tags=tags,
            question_altered_count=altered_count,
        )

    @staticmethod
    def _assert_category_exists(cur, category_id: Optional[int]) -> None:
        if category_id is None:
            return
        cur.execute("SELECT 1 FROM category WHERE id = %s", (category_id,))
        if cur.fetchone() is None:
            raise QaError(f"category id={category_id} does not exist")

    @staticmethod
    def _assert_tags_exist(cur, tag_ids: Optional[List[int]]) -> None:
        if not tag_ids:
            return
        cur.execute("SELECT id FROM tag WHERE id = ANY(%s)", (list(tag_ids),))
        found = {r[0] for r in cur.fetchall()}
        missing = [tid for tid in tag_ids if tid not in found]
        if missing:
            raise QaError(f"tag ids do not exist: {missing}")
