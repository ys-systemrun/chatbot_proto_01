"""検証機能の永続化（IMPL-202608260909 T7 / ADR-0048・0050、IMPL-202608261022 T13）。

既存 conversation_db/db.py と同様、psycopg2 によるコンテキストマネージャーとして実装する。
接続先は既存の CONVERSATION_DB_URL（conversation データベース）。verification_* 4テーブルへの
参照・登録・評価保存を担う。

一覧・詳細のタグ／情報源取得は、対象 run_id をまとめた1回のクエリ（WHERE run_id = ANY(%s)）で
行い、質問（または実行）の件数分ループしてクエリを発行しない（0章 / 10章 N+1回避）。

path / metadata は TEXT 列であり、INSERT 時に json.dumps、読み出し時に json.loads する。
空リスト・空辞書も "[]"／"{}" として保存し、None と区別する（10章）。
"""

from __future__ import annotations

import json

import psycopg2

from .models import (
    VerificationQuestionRecord,
    VerificationRunRecord,
    VerificationSourceRecord,
    VerificationTagRecord,
)

# verification_run の SELECT カラム順（_row_to_run が位置で参照する）。
_RUN_COLS = (
    "id, question_id, executed_at, status, error_message, "
    "max_tags, confidence_threshold, top_k, min_score, "
    "tag_selector_latency_ms, knowledge_mcp_latency_ms, "
    "evaluation, evaluation_comment, evaluated_at, existing_tags_snapshot"  # IMPL-202608261510 T3
)


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


class VerificationDB:
    """検証質問・実行履歴の参照／登録／評価を行うコンテキストマネージャー。"""

    def __init__(self, url: str) -> None:
        self._url = url
        self._conn = None

    def __enter__(self) -> "VerificationDB":
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

    # ------------------------------------------------------------------ #
    # 参照系
    # ------------------------------------------------------------------ #
    def list_questions(
        self, keyword: str | None, limit: int, offset: int
    ) -> tuple[list[VerificationQuestionRecord], int]:
        """質問一覧（created_at DESC）と総件数を返す。各質問には最終実行のみを結合する。"""
        conditions: list[str] = []
        params: list = []
        if keyword:
            conditions.append("(q.question_text ILIKE %s OR q.memo ILIKE %s)")
            like = f"%{keyword}%"
            params.extend([like, like])
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with self._conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM verification_question q {where}", params)
            total = cur.fetchone()[0]

            cur.execute(
                f"""
                SELECT
                    q.id, q.question_text, q.memo, q.created_at, q.updated_at, q.existing_tags,
                    {', '.join('r.' + c for c in _run_col_names())}
                FROM verification_question q
                LEFT JOIN LATERAL (
                    SELECT * FROM verification_run
                    WHERE question_id = q.id
                    ORDER BY executed_at DESC
                    LIMIT 1
                ) r ON true
                {where}
                ORDER BY q.created_at DESC, q.id DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()

        questions: list[VerificationQuestionRecord] = []
        runs_by_id: dict[int, VerificationRunRecord] = {}
        for row in rows:
            q = VerificationQuestionRecord(
                id=row[0],
                question_text=row[1],
                memo=row[2],
                created_at=_iso(row[3]) or "",
                updated_at=_iso(row[4]) or "",
                existing_tags=json.loads(row[5]) if row[5] else [],  # IMPL-202608261510 T3
            )
            if row[6] is not None:  # r.id -> 最終実行あり（旧: row[5]）
                run = self._row_to_run(row[6:])
                q.latest_run = run
                runs_by_id[run.id] = run
            questions.append(q)

        self._attach_tags_sources(runs_by_id)
        return questions, total

    def get_question(self, question_id: int) -> VerificationQuestionRecord | None:
        """最終実行のみを含む軽量版（run_question 実行前の存在確認に使う）。"""
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, question_text, memo, created_at, updated_at, existing_tags"
                " FROM verification_question WHERE id = %s",
                (question_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            q = VerificationQuestionRecord(
                id=row[0],
                question_text=row[1],
                memo=row[2],
                created_at=_iso(row[3]) or "",
                updated_at=_iso(row[4]) or "",
                existing_tags=json.loads(row[5]) if row[5] else [],  # IMPL-202608261510 T3
            )
            cur.execute(
                f"SELECT {_RUN_COLS} FROM verification_run"
                " WHERE question_id = %s ORDER BY executed_at DESC LIMIT 1",
                (question_id,),
            )
            run_row = cur.fetchone()
        if run_row is not None:
            run = self._row_to_run(run_row)
            q.latest_run = run
            self._attach_tags_sources({run.id: run})
        return q

    def get_question_detail(self, question_id: int) -> VerificationQuestionRecord | None:
        """全実行履歴（executed_at DESC）を runs に格納した詳細版。"""
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, question_text, memo, created_at, updated_at, existing_tags"
                " FROM verification_question WHERE id = %s",
                (question_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            q = VerificationQuestionRecord(
                id=row[0],
                question_text=row[1],
                memo=row[2],
                created_at=_iso(row[3]) or "",
                updated_at=_iso(row[4]) or "",
                existing_tags=json.loads(row[5]) if row[5] else [],  # IMPL-202608261510 T3
            )
            cur.execute(
                f"SELECT {_RUN_COLS} FROM verification_run"
                " WHERE question_id = %s ORDER BY executed_at DESC",
                (question_id,),
            )
            run_rows = cur.fetchall()

        runs_by_id: dict[int, VerificationRunRecord] = {}
        for run_row in run_rows:
            run = self._row_to_run(run_row)
            q.runs.append(run)
            runs_by_id[run.id] = run
        self._attach_tags_sources(runs_by_id)
        return q

    # ------------------------------------------------------------------ #
    # 質問 CRUD
    # ------------------------------------------------------------------ #
    def create_question(
        self, question_text: str, memo: str | None, existing_tags: list[str] | None = None
    ) -> VerificationQuestionRecord:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO verification_question (question_text, memo, existing_tags)"
                " VALUES (%s, %s, %s) RETURNING id, created_at, updated_at",
                (question_text, memo, json.dumps(existing_tags) if existing_tags else None),
            )
            new_id, created_at, updated_at = cur.fetchone()
        return VerificationQuestionRecord(
            id=new_id,
            question_text=question_text,
            memo=memo,
            created_at=_iso(created_at) or "",
            updated_at=_iso(updated_at) or "",
            existing_tags=list(existing_tags or []),  # IMPL-202608261510 T3
        )

    def update_question(
        self,
        question_id: int,
        question_text: str | None,
        memo: str | None,
        existing_tags: list[str] | None = None,
    ) -> VerificationQuestionRecord | None:
        """送られた項目のみ更新する（未指定フィールドは変更なし）。updated_at も更新する。"""
        set_clauses: list[str] = []
        params: list = []
        if question_text is not None:
            set_clauses.append("question_text = %s")
            params.append(question_text)
        if memo is not None:
            set_clauses.append("memo = %s")
            params.append(memo)
        if existing_tags is not None:  # None は変更なし、空配列を含む値は置き換え（0章）。IMPL-202608261510 T3
            set_clauses.append("existing_tags = %s")
            params.append(json.dumps(existing_tags))
        set_clauses.append("updated_at = NOW()")

        with self._conn.cursor() as cur:
            cur.execute("SELECT 1 FROM verification_question WHERE id = %s", (question_id,))
            if cur.fetchone() is None:
                return None
            cur.execute(
                f"UPDATE verification_question SET {', '.join(set_clauses)} WHERE id = %s",
                params + [question_id],
            )
        return self.get_question(question_id)

    def delete_question(self, question_id: int) -> bool:
        """ON DELETE CASCADE により実行履歴も削除される。"""
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM verification_question WHERE id = %s", (question_id,)
            )
            return cur.rowcount > 0

    def bulk_create_questions(self, rows: list[dict]) -> list[dict]:
        """CSV 由来の複数行をまとめて登録する（IMPL-202608261022 T13、ADR-0054）。

        question_text が空文字の行はスキップしエラーとして報告する（重複チェックは行わない, #8）。
        行ごとに独立してコミットし、1行のエラーが他行に波及しないようにする。
        """
        results: list[dict] = []
        for i, row in enumerate(rows):
            text = (row.get("question_text") or "").strip()
            if not text:
                results.append(
                    {"row": i, "status": "error", "error": "question_text is required"}
                )
                continue
            try:
                with self._conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO verification_question (question_text, memo)"
                        " VALUES (%s, %s) RETURNING id",
                        (text, row.get("memo") or None),
                    )
                    new_id = cur.fetchone()[0]
                self._conn.commit()
                results.append({"row": i, "status": "success", "id": new_id})
            except Exception as e:  # noqa: BLE001 - 行単位エラー許容
                self._conn.rollback()
                results.append({"row": i, "status": "error", "error": str(e)})
        return results

    # ------------------------------------------------------------------ #
    # 実行結果・評価
    # ------------------------------------------------------------------ #
    def create_run(
        self,
        question_id: int,
        question_text_snapshot: str,
        status: str,
        error_message: str | None,
        max_tags: int | None,
        confidence_threshold: float | None,
        top_k: int | None,
        min_score: float | None,
        tag_selector_latency_ms: int | None,
        knowledge_mcp_latency_ms: int | None,
        existing_tags_snapshot: list[str],  # IMPL-202608261510 T3
        tags: list[VerificationTagRecord],
        sources: list[VerificationSourceRecord],
    ) -> VerificationRunRecord:
        """verification_run とタグ・情報源を1トランザクションで登録する（ADR-0050）。"""
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO verification_run (
                    question_id, question_text_snapshot, status, error_message,
                    max_tags, confidence_threshold, top_k, min_score,
                    tag_selector_latency_ms, knowledge_mcp_latency_ms, existing_tags_snapshot
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, executed_at
                """,
                (
                    question_id,
                    question_text_snapshot,
                    status,
                    error_message,
                    max_tags,
                    confidence_threshold,
                    top_k,
                    min_score,
                    tag_selector_latency_ms,
                    knowledge_mcp_latency_ms,
                    json.dumps(existing_tags_snapshot or []),
                ),
            )
            run_id, executed_at = cur.fetchone()

            for t in tags:
                cur.execute(
                    "INSERT INTO verification_run_tag"
                    " (run_id, rank_no, tag_id, tag_name, score, path)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        run_id,
                        t.rank_no,
                        t.tag_id,
                        t.tag_name,
                        t.score,
                        json.dumps(t.path or []),
                    ),
                )
            for s in sources:
                cur.execute(
                    "INSERT INTO verification_run_source"
                    " (run_id, rank_no, source_id, source_type, title, content, score, metadata)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        run_id,
                        s.rank_no,
                        s.source_id,
                        s.source_type,
                        s.title,
                        s.content,
                        s.score,
                        json.dumps(s.metadata or {}),
                    ),
                )

        return VerificationRunRecord(
            id=run_id,
            question_id=question_id,
            executed_at=_iso(executed_at) or "",
            status=status,
            error_message=error_message,
            max_tags=max_tags,
            confidence_threshold=confidence_threshold,
            top_k=top_k,
            min_score=min_score,
            tag_selector_latency_ms=tag_selector_latency_ms,
            knowledge_mcp_latency_ms=knowledge_mcp_latency_ms,
            evaluation=None,
            evaluation_comment=None,
            evaluated_at=None,
            existing_tags_snapshot=list(existing_tags_snapshot or []),  # IMPL-202608261510 T3
            tags=list(tags),
            sources=list(sources),
        )

    def save_evaluation(
        self, run_id: int, evaluation: int, comment: str | None
    ) -> VerificationRunRecord | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE verification_run"
                " SET evaluation = %s, evaluation_comment = %s, evaluated_at = NOW()"
                " WHERE id = %s",
                (evaluation, comment, run_id),
            )
            if cur.rowcount == 0:
                return None
            cur.execute(
                f"SELECT {_RUN_COLS} FROM verification_run WHERE id = %s", (run_id,)
            )
            run = self._row_to_run(cur.fetchone())
        self._attach_tags_sources({run.id: run})
        return run

    # ------------------------------------------------------------------ #
    # 内部ヘルパ
    # ------------------------------------------------------------------ #
    def _row_to_run(self, row) -> VerificationRunRecord:
        return VerificationRunRecord(
            id=row[0],
            question_id=row[1],
            executed_at=_iso(row[2]) or "",
            status=row[3],
            error_message=row[4],
            max_tags=row[5],
            confidence_threshold=row[6],
            top_k=row[7],
            min_score=row[8],
            tag_selector_latency_ms=row[9],
            knowledge_mcp_latency_ms=row[10],
            evaluation=row[11],
            evaluation_comment=row[12],
            evaluated_at=_iso(row[13]),
            existing_tags_snapshot=json.loads(row[14]) if row[14] else [],  # IMPL-202608261510 T3
        )

    def _attach_tags_sources(
        self, runs_by_id: dict[int, VerificationRunRecord]
    ) -> None:
        """対象 run_id のタグ・情報源を各1クエリで取得し、run へ詰める（N+1回避）。"""
        if not runs_by_id:
            return
        run_ids = list(runs_by_id.keys())
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT run_id, rank_no, tag_id, tag_name, score, path"
                " FROM verification_run_tag"
                " WHERE run_id = ANY(%s) ORDER BY run_id, rank_no",
                (run_ids,),
            )
            for r in cur.fetchall():
                runs_by_id[r[0]].tags.append(
                    VerificationTagRecord(
                        rank_no=r[1],
                        tag_id=r[2],
                        tag_name=r[3],
                        score=r[4],
                        path=json.loads(r[5]) if r[5] else [],
                    )
                )
            cur.execute(
                "SELECT run_id, rank_no, source_id, source_type, title, content, score, metadata"
                " FROM verification_run_source"
                " WHERE run_id = ANY(%s) ORDER BY run_id, rank_no",
                (run_ids,),
            )
            for r in cur.fetchall():
                runs_by_id[r[0]].sources.append(
                    VerificationSourceRecord(
                        rank_no=r[1],
                        source_id=r[2],
                        source_type=r[3],
                        title=r[4],
                        content=r[5],
                        score=r[6],
                        metadata=json.loads(r[7]) if r[7] else {},
                    )
                )


def _run_col_names() -> list[str]:
    """_RUN_COLS を LATERAL 別名（r.*）で参照するための列名リスト。"""
    return [c.strip() for c in _RUN_COLS.split(",")]
