"""QaManagementRepository（実装指示書 4.1 / T1 / ADR-0014）。

qa_original / question_altered / qa_tag への CRUD と、question_text の embedding 計算を提供する。
既存 QARepository（ベクトル類似検索）とは別に、管理UI向けの単純な条件検索・登録・編集を担う。

**内部状態としてQA・タグ情報をキャッシュしないこと**（ADR-0006の設計方針を踏襲。都度DB参照）。
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from ..db.connection import Database, to_vector_str
from ..models.qa import QaDetail, QaError, QaSummary
from .tag_repository import TagError

if TYPE_CHECKING:
    from .tag_repository import TagRepository


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
                "(hiroba_qa_original.title ILIKE %s"
                " OR hiroba_qa_original.question_text ILIKE %s"
                " OR hiroba_qa_original.answer_text ILIKE %s)"
            )
            like = f"%{keyword}%"
            params.extend([like, like, like])

        if category:
            conditions.append(
                "hiroba_qa_original.category_id = (SELECT id FROM hiroba_category WHERE name = %s)"
            )
            params.append(category)

        if tag_ids:
            # 指定タグIDをすべて持つQAのみに絞り込む（AND条件・完全一致）。
            conditions.append(
                """(
                    SELECT COUNT(DISTINCT qt.tag_id)
                    FROM hiroba_qa_tag qt
                    WHERE qt.qa_id = hiroba_qa_original.uuid
                      AND qt.tag_id = ANY(%s)
                ) = %s"""
            )
            params.append(list(tag_ids))
            params.append(len(set(tag_ids)))

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        count_sql = f"SELECT COUNT(*) FROM hiroba_qa_original {where_clause}"

        list_sql = f"""
            SELECT
                hiroba_qa_original.uuid AS qa_id,
                hiroba_qa_original.title AS title,
                hiroba_category.name AS category_name,
                COALESCE(
                    (
                        SELECT array_agg(tag.name ORDER BY tag.name)
                        FROM hiroba_qa_tag
                        JOIN tag ON tag.id = hiroba_qa_tag.tag_id
                        WHERE hiroba_qa_tag.qa_id = hiroba_qa_original.uuid
                    ),
                    ARRAY[]::text[]
                ) AS tags,
                (
                    SELECT COUNT(*)
                    FROM hiroba_question_altered
                    WHERE hiroba_question_altered.qa_id = hiroba_qa_original.uuid
                ) AS hiroba_question_altered_count
            FROM hiroba_qa_original
            LEFT JOIN hiroba_category ON hiroba_qa_original.category_id = hiroba_category.id
            {where_clause}
            ORDER BY hiroba_qa_original.title NULLS LAST, hiroba_qa_original.uuid
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
                hiroba_question_altered_count=row[4],
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
            cur.execute("SELECT id, name FROM hiroba_category ORDER BY id")
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
                INSERT INTO hiroba_qa_original (uuid, question_text, answer_text, category_id, title)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (qa_id, question_text, answer_text, category_id, title),
            )
            # 主となる質問文行（is_primary=true）を1件生成する。
            cur.execute(
                """
                INSERT INTO hiroba_question_altered (qa_id, text, embedding, is_primary)
                VALUES (%s, %s, %s, true)
                """,
                (qa_id, question_text, vec_str),
            )
            if tag_ids:
                cur.executemany(
                    "INSERT INTO hiroba_qa_tag (qa_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
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
                    f"UPDATE hiroba_qa_original SET {', '.join(set_clauses)} WHERE uuid = %s",
                    set_params + [qa_id],
                )

            # question_text 変更時: is_primary=true の1件のみ text/embedding を再計算。
            if question_text is not None:
                cur.execute(
                    """
                    UPDATE hiroba_question_altered
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
                        INSERT INTO hiroba_question_altered (qa_id, text, embedding, is_primary)
                        VALUES (%s, %s, %s, true)
                        """,
                        (qa_id, question_text, vec_str),
                    )

            # tag_ids 指定時: qa_tag を指定集合で置き換える（None は変更なし、[] は全解除）。
            if tag_ids is not None:
                cur.execute("DELETE FROM hiroba_qa_tag WHERE qa_id = %s", (qa_id,))
                if tag_ids:
                    cur.executemany(
                        "INSERT INTO hiroba_qa_tag (qa_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        [(qa_id, tid) for tid in tag_ids],
                    )

            detail = self._load_detail(cur, qa_id)
        return detail

    def delete_qa(self, qa_id: str) -> None:
        """QA（qa_original）を、紐づく qa_tag・question_altered ごとカスケード削除する（ADR-0067）。

        まず対象QAの存在を検証し（get_qa と同様）、存在しなければ QaError を送出する。
        存在する場合は同一トランザクション内で、
          qa_tag（外部キー制約上 qa_original より先に削除する必要がある）
          → question_altered（is_primary を問わず全件。主質問文行も削除する）
          → qa_original
        の順に削除し、孤立行（qa_id が存在しない question_altered）が残らないようにする。

        検証実行履歴（verification_run_source）・会話ログへの参照は、chatbot と
        conversation データベース間に外部キー制約がないため（ADR-0048）カスケードしない。
        削除後もこれらの参照は残存し得る（利用者への告知は front_dev の確認ダイアログで行う）。
        """
        with self.db.cursor() as cur:
            if self._load_detail(cur, qa_id) is None:
                raise QaError(f"qa id={qa_id} does not exist")

            # qa_tag → question_altered → qa_original の順に、同一トランザクションで削除する。
            cur.execute("DELETE FROM hiroba_qa_tag WHERE qa_id = %s", (qa_id,))
            cur.execute("DELETE FROM hiroba_question_altered WHERE qa_id = %s", (qa_id,))
            cur.execute("DELETE FROM hiroba_qa_original WHERE uuid = %s", (qa_id,))

    # ------------------------------------------------------------------ #
    # CSV 一括インポート（IMPL-202608261022 T9 / ADR-0053）
    # ------------------------------------------------------------------ #
    def import_qa_batch(
        self,
        rows: List[dict],
        tag_repository: "TagRepository",
    ) -> List[dict]:
        """CSVの各行をまとめて登録・更新する。行ごとに独立してコミットし、1行のエラーが
        他行に波及しないようにする（ADR-0053）。

        - `uuid` が空: create_qa 相当（新規作成、qa_id は自動採番）。
        - `uuid` が既存: update_qa 相当（部分更新。CSVの列が空の項目は変更しない, #12）。
        - `tags`: タグ名のカンマ区切り。既存タグは名前で解決、未存在は自動作成する（#7）。
        - 戻り値: [{"row", "status", "qa_id"?, "error"?}, ...]
        """
        results: List[dict] = []
        for i, row in enumerate(rows):
            try:
                tag_ids = self._resolve_tag_names(row.get("tags"), tag_repository)
                category_id = self._parse_category_id(row.get("category_id"))
                if row.get("uuid"):
                    detail = self.update_qa(
                        row["uuid"],
                        title=row.get("title") or None,
                        question_text=row.get("question_text") or None,
                        answer_text=row.get("answer_text") or None,
                        category_id=category_id,
                        # tags 列が空欄なら「変更なし」（None）。値があるときのみ置換する。
                        tag_ids=tag_ids if row.get("tags") else None,
                    )
                else:
                    detail = self.create_qa(
                        title=row.get("title") or "",
                        question_text=row.get("question_text") or "",
                        answer_text=row.get("answer_text") or "",
                        category_id=category_id,
                        tag_ids=tag_ids,
                    )
                results.append({"row": i, "status": "success", "qa_id": detail.id})
            except (QaError, TagError) as e:
                results.append({"row": i, "status": "error", "error": str(e)})
        return results

    def _resolve_tag_names(
        self, tags_field, tag_repository: "TagRepository"
    ) -> Optional[List[int]]:
        """タグ名のカンマ区切り文字列を tag_id のリストへ解決する。未存在タグは自動作成する（#7）。

        空・未指定の場合は None（＝タグ紐付けを変更しない）を返す。
        """
        if not tags_field:
            return None
        names = [t.strip() for t in tags_field.split(",") if t.strip()]
        ids: List[int] = []
        for name in names:
            tag = tag_repository.find_by_name(name)
            if tag is None:
                tag = tag_repository.create_tag(name=name)  # 自動作成（#7）
            ids.append(tag.id)
        return ids

    @staticmethod
    def _parse_category_id(value) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise QaError(f"category_id must be an integer: {value!r}")

    # ------------------------------------------------------------------ #
    # 内部ヘルパ
    # ------------------------------------------------------------------ #
    def _load_detail(self, cur, qa_id: str) -> Optional[QaDetail]:
        cur.execute(
            """
            SELECT
                hiroba_qa_original.uuid,
                hiroba_qa_original.title,
                hiroba_qa_original.question_text,
                hiroba_qa_original.answer_text,
                hiroba_category.id,
                hiroba_category.name
            FROM hiroba_qa_original
            LEFT JOIN hiroba_category ON hiroba_qa_original.category_id = hiroba_category.id
            WHERE hiroba_qa_original.uuid = %s
            """,
            (qa_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None

        cur.execute(
            """
            SELECT tag.id, tag.name
            FROM hiroba_qa_tag
            JOIN tag ON tag.id = hiroba_qa_tag.tag_id
            WHERE hiroba_qa_tag.qa_id = %s
            ORDER BY tag.name
            """,
            (qa_id,),
        )
        tags = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]

        cur.execute(
            "SELECT COUNT(*) FROM hiroba_question_altered WHERE qa_id = %s", (qa_id,)
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
            hiroba_question_altered_count=altered_count,
        )

    @staticmethod
    def _assert_category_exists(cur, category_id: Optional[int]) -> None:
        if category_id is None:
            return
        cur.execute("SELECT 1 FROM hiroba_category WHERE id = %s", (category_id,))
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
