"""QuestionAlteredRepository（IMPL-202608281100 T2 / ADR-0064）。

question_altered の「言い換え行」（is_primary=false）のみを対象とした一覧・詳細・
新規作成・編集・削除・CSV一括インポート・CSVエクスポートを提供する。

主質問文行（is_primary=true）は本リポジトリでは生成・変更・削除しない。書き込み系
（create/update/delete/import）は is_primary=false を不変条件として必ず守り、既存の
create_qa/update_qa（ADR-0014）が前提とする「qa_id ごとに is_primary=true 行は常に1件」
を新機能側から破らないようにする。

**内部状態としてQA情報をキャッシュしないこと**（ADR-0006 の設計方針を踏襲。都度DB参照）。
embedding はネットワーク呼び出しのため、トランザクション外で先に計算する（create_qa と同一）。
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from ..db.connection import Database, to_vector_str
from ..models.question_altered import QuestionAltered, QuestionAlteredError


class QuestionAlteredRepository:
    def __init__(self, db: Database, embed_fn: Callable[[str], List[float]]):
        """
        db: DB接続ファクトリ（都度コネクションを生成する）。
        embed_fn: text をベクトル化する関数（DI、既存 embedding 呼び出しと同等）。
        """
        self.db = db
        self.embed_fn = embed_fn

    # ------------------------------------------------------------------ #
    # 参照系
    # ------------------------------------------------------------------ #
    def list_question_altered(
        self,
        qa_id: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[QuestionAltered], int]:
        """(件数分の QuestionAltered, 絞り込み後の全体件数) を返す。

        is_primary=false のみを対象とし、qa_id（完全一致）・keyword（text 部分一致）で
        絞り込む。表示用に qa_original.title を LEFT JOIN する（外部キー制約なし）。
        """
        conditions: List[str] = ["qa.is_primary = false"]
        params: List = []

        if qa_id:
            conditions.append("qa.qa_id = %s")
            params.append(qa_id)

        if keyword:
            conditions.append("qa.text ILIKE %s")
            params.append(f"%{keyword}%")

        where_clause = "WHERE " + " AND ".join(conditions)

        count_sql = f"SELECT COUNT(*) FROM question_altered qa {where_clause}"

        list_sql = f"""
            SELECT qa.id, qa.qa_id, qo.title, qa.text, qa.is_primary
            FROM question_altered qa
            LEFT JOIN qa_original qo ON qo.uuid = qa.qa_id
            {where_clause}
            ORDER BY qa.text NULLS LAST, qa.id
            LIMIT %s OFFSET %s
        """

        with self.db.cursor() as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()[0]

            cur.execute(list_sql, params + [limit, offset])
            rows = cur.fetchall()

        items = [self._row_to_model(row) for row in rows]
        return items, total

    def get_question_altered(self, item_id: int) -> QuestionAltered:
        """id 指定で1件取得する（存在しなければ QuestionAlteredError）。

        参照系は is_primary を問わず取得する（編集フォームの初期表示用）。書き込み時に
        is_primary=true を拒否するため、参照でブロックする必要はない。
        """
        with self.db.cursor() as cur:
            model = self._load(cur, item_id)
        if model is None:
            raise QuestionAlteredError(f"question_altered id={item_id} does not exist")
        return model

    # ------------------------------------------------------------------ #
    # 更新系（すべて is_primary=false を不変条件として守る）
    # ------------------------------------------------------------------ #
    def create_question_altered(self, qa_id: str, text: str) -> QuestionAltered:
        """qa_id（存在検証）・text から embedding を計算し、is_primary=false で1件追加する。"""
        if not qa_id:
            raise QuestionAlteredError("qa_id is required")
        if not text:
            raise QuestionAlteredError("text is required")

        # embedding はネットワーク呼び出しのためトランザクション外で先に計算する。
        vec_str = to_vector_str(self.embed_fn(text))

        with self.db.cursor() as cur:
            self._assert_qa_exists(cur, qa_id)
            cur.execute(
                """
                INSERT INTO question_altered (qa_id, text, embedding, is_primary)
                VALUES (%s, %s, %s, false)
                RETURNING id
                """,
                (qa_id, text, vec_str),
            )
            new_id = cur.fetchone()[0]
            model = self._load(cur, new_id)
        return model

    def update_question_altered(self, item_id: int, text: str) -> QuestionAltered:
        """対象行の存在と is_primary=false を検証し、text とembeddingを再計算する。

        qa_id の付け替えは提供しない（要件4.2）。対象が is_primary=true の場合は拒否する。
        """
        if not text:
            raise QuestionAlteredError("text is required")

        vec_str = to_vector_str(self.embed_fn(text))

        with self.db.cursor() as cur:
            existing = self._load(cur, item_id)
            if existing is None:
                raise QuestionAlteredError(
                    f"question_altered id={item_id} does not exist"
                )
            if existing.is_primary:
                raise QuestionAlteredError(
                    f"question_altered id={item_id} is a primary row and cannot be edited"
                )
            cur.execute(
                """
                UPDATE question_altered
                SET text = %s, embedding = %s
                WHERE id = %s AND is_primary = false
                """,
                (text, vec_str, item_id),
            )
            model = self._load(cur, item_id)
        return model

    def delete_question_altered(self, item_id: int) -> None:
        """対象行の存在と is_primary=false を検証し、削除する。

        主質問文行（is_primary=true）は本機能を含め削除手段を持たないため、削除自体を提供しない。
        """
        with self.db.cursor() as cur:
            existing = self._load(cur, item_id)
            if existing is None:
                raise QuestionAlteredError(
                    f"question_altered id={item_id} does not exist"
                )
            if existing.is_primary:
                raise QuestionAlteredError(
                    f"question_altered id={item_id} is a primary row and cannot be deleted"
                )
            cur.execute(
                "DELETE FROM question_altered WHERE id = %s AND is_primary = false",
                (item_id,),
            )

    # ------------------------------------------------------------------ #
    # CSV 一括インポート（IMPL-202608281100 T2 / ADR-0064・0053）
    # ------------------------------------------------------------------ #
    def import_question_altered_batch(self, rows: List[dict]) -> List[dict]:
        """CSVの各行（dict: id, qa_id, text, is_primary）をまとめて登録・更新する。

        - `id` が空: create_question_altered 相当（新規作成、is_primary=false 固定）。
        - `id` が既存: update_question_altered 相当（text/embedding 更新）。
          対象が is_primary=true の場合はエラー行として報告する。
          CSVの `qa_id` が空でなく既存行の qa_id と異なる場合は付け替えとしてエラーにする（要件4.2）。
        - `is_primary` 列の値は常に無視する（新機能は is_primary=true を作らない）。
        - 行ごとに独立してコミットし、1行のエラーが他行に波及しないようにする（ADR-0053）。
        - 戻り値: [{"row", "status", "id"?, "error"?}, ...]
        """
        results: List[dict] = []
        for i, row in enumerate(rows):
            try:
                raw_id = (str(row.get("id")) if row.get("id") is not None else "").strip()
                qa_id = (row.get("qa_id") or "").strip()
                text = (row.get("text") or "").strip()

                if raw_id:
                    item_id = self._parse_id(raw_id)
                    self._assert_no_qa_id_reassign(item_id, qa_id)
                    model = self.update_question_altered(item_id, text)
                else:
                    model = self.create_question_altered(qa_id, text)
                results.append({"row": i, "status": "success", "id": model.id})
            except QuestionAlteredError as e:
                results.append({"row": i, "status": "error", "error": str(e)})
        return results

    def _assert_no_qa_id_reassign(self, item_id: int, qa_id: str) -> None:
        """更新行で CSV の qa_id が既存行と異なる場合、付け替えとしてエラーにする（要件4.2）。

        qa_id が空欄の場合は「既存の qa_id を維持」とみなし、チェックしない。
        対象行の不存在・is_primary=true の検証は update_question_altered 側でも行われるが、
        付け替えチェックのためにここで先に読み出す。
        """
        if not qa_id:
            return
        with self.db.cursor() as cur:
            existing = self._load(cur, item_id)
        if existing is None:
            raise QuestionAlteredError(
                f"question_altered id={item_id} does not exist"
            )
        if existing.qa_id != qa_id:
            raise QuestionAlteredError(
                f"qa_id reassignment is not allowed "
                f"(id={item_id}: existing qa_id={existing.qa_id}, csv qa_id={qa_id})"
            )

    # ------------------------------------------------------------------ #
    # CSV エクスポート（IMPL-202608281100 T2 / ADR-0064）
    # ------------------------------------------------------------------ #
    def export_question_altered(self) -> List[dict]:
        """is_primary=false 行の全件を {id, qa_id, text, is_primary} のリストで返す。

        ページングせず全件を返す（CSV 組み立ては web_backend 側で行う）。embedding は含めない。
        """
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT id, qa_id, text, is_primary
                FROM question_altered
                WHERE is_primary = false
                ORDER BY text NULLS LAST, id
                """
            )
            rows = cur.fetchall()
        return [
            {"id": r[0], "qa_id": r[1], "text": r[2], "is_primary": r[3]}
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    # 内部ヘルパ
    # ------------------------------------------------------------------ #
    def _load(self, cur, item_id: int) -> Optional[QuestionAltered]:
        cur.execute(
            """
            SELECT qa.id, qa.qa_id, qo.title, qa.text, qa.is_primary
            FROM question_altered qa
            LEFT JOIN qa_original qo ON qo.uuid = qa.qa_id
            WHERE qa.id = %s
            """,
            (item_id,),
        )
        row = cur.fetchone()
        return self._row_to_model(row) if row is not None else None

    @staticmethod
    def _row_to_model(row) -> QuestionAltered:
        # row: (id, qa_id, title, text, is_primary)
        return QuestionAltered(
            id=row[0],
            qa_id=row[1],
            qa_title=row[2],
            text=row[3] or "",
            is_primary=row[4],
        )

    @staticmethod
    def _parse_id(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            raise QuestionAlteredError(f"id must be an integer: {value!r}")

    @staticmethod
    def _assert_qa_exists(cur, qa_id: str) -> None:
        cur.execute("SELECT 1 FROM qa_original WHERE uuid = %s", (qa_id,))
        if cur.fetchone() is None:
            raise QuestionAlteredError(f"qa id={qa_id} does not exist")
