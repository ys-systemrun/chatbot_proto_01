"""TroubleshootingRepository（ADR-0076 / ADR-0078 / REQ-202609071337 8章）。

トラブルシューティング記事（troubleshooting_article）を search_knowledge のマルチソース検索へ
統合するための Repository。既存 QARepository と同一の Repository インターフェース
（repository/base.py）を実装し、SearchService へ DI 登録するだけで統合が完了する
（SearchService 自体の変更は不要。ADR-0078 決定1）。

QARepository と異なり、記事ごとに単一 embedding を持つ（troubleshooting_article.embedding。
hiroba_question_altered のような言い換え質問の複層構造は持たない, ADR-0078 決定3）。スコアリングは
QARepository と同一（埋め込み距離スコア + 祖先タグ展開後のタグ構成類似度=Jaccard の重み付き合成,
ADR-0058 / ADR-0059）で、重み TAG_SIMILARITY_WEIGHT も共用する（ADR-0078 決定2）。
"""

from __future__ import annotations

from typing import Callable, List, Optional

from ..db.connection import Database, to_vector_str
from ..models.document import Document
from .scoring import distance_to_score, jaccard

SOURCE_TYPE = "troubleshooting"


class TroubleshootingRepository:
    def __init__(
        self,
        db: Database,
        embed_fn: Callable[[str], List[float]],
        tag_similarity_weight: float = 0.5,
        candidate_pool_size: Optional[int] = None,
    ):
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
        # category はトラブルシューティング記事には存在しない分類概念（ADR-0078 決定4）。
        # カテゴリでの絞り込みが指定された場合、本情報源は一件も該当しないため空を返す
        # （QA カテゴリ絞り込みの意味論を尊重する）。通常のチャット検索では category=None。
        if category:
            return []

        embedding = self.embed_fn(query)
        vec_str = to_vector_str(embedding)
        pool_size = self.candidate_pool_size or max(top_k * 10, 50)

        params: dict = {"query_vec": vec_str, "pool_size": pool_size}

        # tags が空/未指定の場合、入力タグ閉包は計算しない（combined_score = embedding_score）。
        tag_names = list(dict.fromkeys(tags)) if tags else []
        params["tag_names"] = tag_names or [None]  # ANY(%(tag_names)s) の空配列/None 区別回避

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
                troubleshooting_article.id AS article_id,
                troubleshooting_article.title AS title,
                troubleshooting_article.subtitle AS subtitle,
                troubleshooting_article.guidance AS guidance,
                troubleshooting_article.source_key AS source_key,
                COALESCE(
                    (SELECT array_agg(tag.name)
                     FROM troubleshooting_article_tag
                     JOIN tag ON tag.id = troubleshooting_article_tag.tag_id
                     WHERE troubleshooting_article_tag.article_id = troubleshooting_article.id),
                    ARRAY[]::text[]
                ) AS tag_names,
                COALESCE(
                    (SELECT array_agg(DISTINCT tc.closure_id)
                     FROM troubleshooting_article_tag at
                     JOIN tag_closure tc ON tc.tag_id = at.tag_id
                     WHERE at.article_id = troubleshooting_article.id),
                    ARRAY[]::integer[]
                ) AS article_closure,
                (SELECT closure FROM input_closure) AS input_closure,
                troubleshooting_article.embedding <=> %(query_vec)s::vector AS distance
            FROM troubleshooting_article
            WHERE troubleshooting_article.embedding IS NOT NULL
            ORDER BY troubleshooting_article.embedding <=> %(query_vec)s::vector
            LIMIT %(pool_size)s
        """

        with self.db.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        input_closure_set: set = set(rows[0][7]) if rows and rows[0][7] else set()
        has_tags = bool(tag_names)

        scored: List[tuple[float, Document]] = []
        for row in rows:
            (
                article_id, title, subtitle, guidance, source_key,
                tag_names_row, article_closure, _input_closure, distance,
            ) = row

            embedding_score = distance_to_score(float(distance))
            metadata = {
                "tags": list(tag_names_row) if tag_names_row else [],
                "category": None,  # 本情報源にカテゴリは存在しない（ADR-0078 §8.5）
                "source_key": source_key,
                "subtitle": subtitle,
            }

            if has_tags:
                tag_similarity = jaccard(input_closure_set, set(article_closure or []))
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
                    id=str(article_id),
                    source_type=SOURCE_TYPE,
                    title=title or "",
                    content=guidance or "",
                    score=combined_score,
                    metadata=metadata,
                ),
            ))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]
