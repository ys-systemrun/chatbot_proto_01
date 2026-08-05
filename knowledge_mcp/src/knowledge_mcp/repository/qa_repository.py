"""QARepository（実装指示書 5.3 / 要件6.3）。

既存 app/src/db.py の search_similar を移植・拡張し、title / category / tags を併せて取得する。
既存 search_similar 同様、question_altered 単位（1 altered question = 1 行）でベクトル近傍を取り、
qa_original / category / tag を結合して Document へ変換する。
"""

from __future__ import annotations

from typing import Callable, List, Optional

from ..db.connection import Database, to_vector_str
from ..models.document import Document

SOURCE_TYPE = "qa"


def distance_to_score(distance: float) -> float:
    """スコア変換式（実装指示書 0節）: score = 1 / (1 + distance)。

    distance は pgvector の <=> 値（小さいほど類似）。暫定式で、精度検証・調整の対象。
    """
    return 1.0 / (1.0 + distance)


class QARepository:
    def __init__(
        self,
        db: Database,
        embed_fn: Callable[[str], List[float]],
    ):
        """
        db: DB接続ファクトリ（都度コネクションを生成する）。
        embed_fn: クエリ文字列を受け取りembeddingベクトルを返す関数（DI）。
                  既存 app/src/embedding.get_embedding と同等のものを想定。
        """
        self.db = db
        self.embed_fn = embed_fn

    def search(
        self,
        query: str,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Document]:
        # 1. クエリをベクトル化
        embedding = self.embed_fn(query)
        vec_str = to_vector_str(embedding)

        # 2. SQL 組み立て（search_similar 相当 + tag/category 結合・フィルタ）
        params: list = [vec_str]  # SELECT 内の <=> 用
        conditions: list[str] = []

        if category:
            conditions.append(
                "qa_original.category_id = (SELECT id FROM category WHERE name = %s)"
            )
            params.append(category)

        if tags:
            # 指定タグをすべて持つQAのみに絞り込む（完全一致・AND条件）。
            # タグ階層(parent_tag_id)を辿った展開はMVPでは行わない（ADR-0005）。
            conditions.append(
                """(
                    SELECT COUNT(DISTINCT t.name)
                    FROM qa_tag qt
                    JOIN tag t ON t.id = qt.tag_id
                    WHERE qt.qa_id = qa_original.uuid
                      AND t.name = ANY(%s)
                ) = %s"""
            )
            params.append(list(tags))
            params.append(len(set(tags)))

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # ORDER BY / LIMIT 用パラメータ
        params.append(vec_str)  # ORDER BY <=> 用
        params.append(top_k)

        sql = f"""
            SELECT
                qa_original.uuid AS qa_id,
                qa_original.title AS title,
                qa_original.answer_text AS answer,
                qa_original.question_text AS question_original,
                question_altered.text AS question,
                category.name AS category_name,
                COALESCE(
                    (
                        SELECT array_agg(tag.name)
                        FROM qa_tag
                        JOIN tag ON tag.id = qa_tag.tag_id
                        WHERE qa_tag.qa_id = qa_original.uuid
                    ),
                    ARRAY[]::text[]
                ) AS tags,
                question_altered.embedding <=> %s AS distance
            FROM question_altered
            LEFT JOIN qa_original ON question_altered.qa_id = qa_original.uuid
            LEFT JOIN category ON qa_original.category_id = category.id
            {where_clause}
            ORDER BY question_altered.embedding <=> %s
            LIMIT %s
        """

        with self.db.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        # 3-4. Document へ変換 + スコア化
        documents: List[Document] = []
        for row in rows:
            (
                qa_id,
                title,
                answer,
                _question_original,
                _question,
                category_name,
                tag_names,
                distance,
            ) = row

            documents.append(
                Document(
                    id=qa_id,
                    source_type=SOURCE_TYPE,
                    title=title or "",
                    content=answer or "",
                    score=distance_to_score(float(distance)),
                    metadata={
                        "tags": list(tag_names) if tag_names else [],
                        "category": category_name,
                        "guid": qa_id,
                    },
                )
            )

        return documents
