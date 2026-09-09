"""QARepository（実装指示書 5.3 / 要件6.3、IMPL-202608261450 T1 で祖先タグ展開・
タグ構成類似度スコアリングに対応）。

既存 app/src/db.py の search_similar を移植・拡張し、title / category / tags を併せて取得する。
既存 search_similar 同様、question_altered 単位（1 altered question = 1 行）でベクトル近傍を取り、
qa_original / category / tag を結合して Document へ変換する。

IMPL-202608261450 により、tags 引数は「AND完全一致のハードフィルタ」から「タグ構成類似度
（祖先タグを含めたJaccard係数）と埋め込み類似度を重み付き合成した総合スコアへ反映するソフトな
シグナル」へ変更された（ADR-0058・ADR-0059）。
"""

from __future__ import annotations

from typing import Callable, List, Optional

from ..db.connection import Database, to_vector_str
from ..models.document import Document
# スコアリングヘルパーは TroubleshootingRepository と共通化した（ADR-0078）。
# 後方互換のため distance_to_score / _jaccard の名前で引き続き本モジュールから参照可能にする。
from .scoring import distance_to_score  # noqa: F401  (re-export)
from .scoring import jaccard as _jaccard  # noqa: F401  (re-export)

SOURCE_TYPE = "qa"


class QARepository:
    def __init__(
        self,
        db: Database,
        embed_fn: Callable[[str], List[float]],
        tag_similarity_weight: float = 0.5,
        candidate_pool_size: Optional[int] = None,
    ):
        """
        db: DB接続ファクトリ（都度コネクションを生成する）。
        embed_fn: クエリ文字列を受け取りembeddingベクトルを返す関数（DI）。
        tag_similarity_weight: 総合スコアにおけるタグ類似度の重み w（0.0〜1.0）。
            環境変数 TAG_SIMILARITY_WEIGHT（既定 0.5）。ADR-0059。
        candidate_pool_size: 候補プールの固定件数。None の場合は呼び出しごとに
            max(top_k * 10, 50) を用いる（環境変数 SEARCH_CANDIDATE_POOL_SIZE 未設定時の既定挙動）。
        """
        self.db = db
        self.embed_fn = embed_fn
        self.tag_similarity_weight = tag_similarity_weight
        self.candidate_pool_size = candidate_pool_size

    def search(
        self,
        query: str,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Document]:
        embedding = self.embed_fn(query)
        vec_str = to_vector_str(embedding)
        pool_size = self.candidate_pool_size or max(top_k * 10, 50)

        conditions: list[str] = []
        params: dict = {"query_vec": vec_str, "pool_size": pool_size}

        if category:
            conditions.append(
                "hiroba_qa_original.category_id = (SELECT id FROM hiroba_category WHERE name = %(category)s)"
            )
            params["category"] = category

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        # tags が空/未指定の場合、入力タグ閉包は計算しない（後段で combined_score = embedding_score
        # とする分岐に使う。要件定義書6.2節）。
        tag_names = list(dict.fromkeys(tags)) if tags else []
        params["tag_names"] = tag_names or [None]  # ANY(%(tag_names)s) が空配列と None を区別しないよう [None] を渡す

        sql = """
            WITH RECURSIVE tag_closure(tag_id, closure_id) AS (
                SELECT id, id FROM tag
                UNION ALL
                SELECT tc.tag_id, t.parent_tag_id
                FROM tag_closure tc
                JOIN tag t ON t.id = tc.closure_id
                WHERE t.parent_tag_id IS NOT NULL
            ),
            input_closure AS (
                SELECT COALESCE(array_agg(DISTINCT tc.closure_id), ARRAY[]::integer[]) AS closure
                FROM tag_closure tc
                WHERE tc.tag_id IN (SELECT id FROM tag WHERE name = ANY(%(tag_names)s))
            )
            SELECT
                hiroba_qa_original.uuid AS qa_id,
                hiroba_qa_original.title AS title,
                hiroba_qa_original.answer_text AS answer,
                hiroba_category.name AS category_name,
                COALESCE(
                    (SELECT array_agg(tag.name) FROM hiroba_qa_tag JOIN tag ON tag.id = hiroba_qa_tag.tag_id
                     WHERE hiroba_qa_tag.qa_id = hiroba_qa_original.uuid),
                    ARRAY[]::text[]
                ) AS tag_names,
                COALESCE(
                    (SELECT array_agg(DISTINCT tc.closure_id)
                     FROM hiroba_qa_tag qt JOIN tag_closure tc ON tc.tag_id = qt.tag_id
                     WHERE qt.qa_id = hiroba_qa_original.uuid),
                    ARRAY[]::integer[]
                ) AS qa_closure,
                (SELECT closure FROM input_closure) AS input_closure,
                hiroba_question_altered.embedding <=> %(query_vec)s::vector AS distance
            FROM hiroba_question_altered
            LEFT JOIN hiroba_qa_original ON hiroba_question_altered.qa_id = hiroba_qa_original.uuid
            LEFT JOIN hiroba_category ON hiroba_qa_original.category_id = hiroba_category.id
            {where_clause}
            ORDER BY hiroba_question_altered.embedding <=> %(query_vec)s::vector
            LIMIT %(pool_size)s
        """.format(where_clause=where_clause)

        with self.db.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        input_closure_set: set = set(rows[0][6]) if rows and rows[0][6] else set()
        has_tags = bool(tag_names)

        scored: List[tuple[float, Document]] = []
        for row in rows:
            (
                qa_id, title, answer, category_name,
                tag_names_row, qa_closure, _input_closure, distance,
            ) = row

            embedding_score = distance_to_score(float(distance))
            metadata = {
                "tags": list(tag_names_row) if tag_names_row else [],
                "category": category_name,
                "guid": qa_id,
            }

            if has_tags:
                tag_similarity = _jaccard(input_closure_set, set(qa_closure or []))
                w = self.tag_similarity_weight
                combined_score = (1 - w) * embedding_score + w * tag_similarity
                metadata["embedding_score"] = embedding_score
                metadata["tag_similarity"] = tag_similarity
                metadata["tag_similarity_weight"] = w
            else:
                combined_score = embedding_score

            scored.append((
                combined_score,
                Document(
                    id=qa_id,
                    source_type=SOURCE_TYPE,
                    title=title or "",
                    content=answer or "",
                    score=combined_score,
                    metadata=metadata,
                ),
            ))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]
