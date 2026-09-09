"""TroubleshootingManagementRepository（ADR-0079 / REQ-202609071337 9章）。

トラブルシューティング記事（troubleshooting_article / troubleshooting_article_tag）への
管理UI向け CRUD を提供する。QaManagementRepository と同様の構成で、一覧・詳細・更新・タグ付けを
担う（新規作成・削除は初期スコープ外, ADR-0079 決定3）。

- 内部状態はキャッシュしない（都度DB参照, ADR-0006 の方針を踏襲）。
- 更新時、埋め込み元テキスト（title + subtitle + symptom + cause + guidance, ADR-0078 §8.3）に
  関わるフィールドが変更された場合は embedding を同期再計算する（要件定義書 Open Issue #2 は
  「保存時同期再計算」で確定）。
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from ..db.connection import Database, to_vector_str
from ..models.troubleshooting import (
    TroubleshootingDetail,
    TroubleshootingError,
    TroubleshootingSummary,
)

# 管理UIから編集可能なテキストフィールド（source_key / body_html / source_updated_at は編集不可）。
EDITABLE_FIELDS = [
    "title",
    "subtitle",
    "symptom",
    "operation_history",
    "error_code",
    "error_message",
    "system_environment",
    "hardware_environment",
    "version_info",
    "guidance",
    "cause",
    "notes",
    "keyword_raw",
]

# NOT NULL 列（空文字での更新を拒否する）。
_NOT_NULL_FIELDS = {"title", "guidance"}

# embedding 元テキストを構成するフィールド（ADR-0078 §8.3）。いずれかの変更で embedding を再計算する。
_EMBEDDING_SOURCE_FIELDS = ["title", "subtitle", "symptom", "cause", "guidance"]


def build_embedding_text(
    title: Optional[str],
    subtitle: Optional[str],
    symptom: Optional[str],
    cause: Optional[str],
    guidance: Optional[str],
) -> str:
    """埋め込み元テキストを組み立てる（troubleshooting_import.build_embedding_text と同一方針）。"""
    parts = [title, subtitle, symptom, cause, guidance]
    return "\n".join(p for p in parts if p).strip()


class TroubleshootingManagementRepository:
    def __init__(self, db: Database, embed_fn: Callable[[str], List[float]]):
        self.db = db
        self.embed_fn = embed_fn

    # ------------------------------------------------------------------ #
    # 参照系
    # ------------------------------------------------------------------ #
    def list_articles(
        self,
        keyword: Optional[str] = None,
        source_key: Optional[str] = None,
        tag_ids: Optional[List[int]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[TroubleshootingSummary], int]:
        conditions: List[str] = []
        params: List = []

        if keyword:
            conditions.append(
                "(troubleshooting_article.title ILIKE %s"
                " OR troubleshooting_article.symptom ILIKE %s"
                " OR troubleshooting_article.guidance ILIKE %s)"
            )
            like = f"%{keyword}%"
            params.extend([like, like, like])

        if source_key:
            conditions.append("troubleshooting_article.source_key = %s")
            params.append(source_key)

        if tag_ids:
            conditions.append(
                """(
                    SELECT COUNT(DISTINCT at.tag_id)
                    FROM troubleshooting_article_tag at
                    WHERE at.article_id = troubleshooting_article.id
                      AND at.tag_id = ANY(%s)
                ) = %s"""
            )
            params.append(list(tag_ids))
            params.append(len(set(tag_ids)))

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        count_sql = f"SELECT COUNT(*) FROM troubleshooting_article {where_clause}"

        list_sql = f"""
            SELECT
                troubleshooting_article.id,
                troubleshooting_article.source_key,
                troubleshooting_article.title,
                troubleshooting_article.subtitle,
                COALESCE(
                    (
                        SELECT array_agg(tag.name ORDER BY tag.name)
                        FROM troubleshooting_article_tag
                        JOIN tag ON tag.id = troubleshooting_article_tag.tag_id
                        WHERE troubleshooting_article_tag.article_id = troubleshooting_article.id
                    ),
                    ARRAY[]::text[]
                ) AS tags,
                troubleshooting_article.source_updated_at
            FROM troubleshooting_article
            {where_clause}
            ORDER BY troubleshooting_article.source_key,
                     troubleshooting_article.title,
                     troubleshooting_article.id
            LIMIT %s OFFSET %s
        """

        with self.db.cursor() as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()[0]

            cur.execute(list_sql, params + [limit, offset])
            rows = cur.fetchall()

        summaries = [
            TroubleshootingSummary(
                id=row[0],
                source_key=row[1],
                title=row[2] or "",
                subtitle=row[3],
                tags=list(row[4]) if row[4] else [],
                source_updated_at=row[5],
            )
            for row in rows
        ]
        return summaries, total

    def get_article(self, article_id: int) -> TroubleshootingDetail:
        with self.db.cursor() as cur:
            detail = self._load_detail(cur, article_id)
        if detail is None:
            raise TroubleshootingError(
                f"troubleshooting article id={article_id} does not exist"
            )
        return detail

    def list_source_keys(self) -> List[str]:
        """投入済みの source_key の一覧を返す（一覧画面の絞り込みプルダウン用）。"""
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT source_key FROM troubleshooting_article ORDER BY source_key"
            )
            return [r[0] for r in cur.fetchall()]

    # ------------------------------------------------------------------ #
    # 更新系（新規作成・削除は初期スコープ外, ADR-0079 決定3）
    # ------------------------------------------------------------------ #
    def update_article(
        self,
        article_id: int,
        fields: Optional[dict] = None,
        tag_ids: Optional[List[int]] = None,
    ) -> TroubleshootingDetail:
        """記事を部分更新する。

        - fields: EDITABLE_FIELDS のうち更新するものだけを含む dict（キー未含=変更なし）。
          NOT NULL 列（title / guidance）に空文字を指定した場合はエラー。
        - tag_ids: None=変更なし、[]=全解除、[...]=指定集合で置換。
        - 埋め込み元フィールド（title/subtitle/symptom/cause/guidance）が変わった場合は
          embedding を同期再計算する。
        """
        fields = fields or {}
        unknown = set(fields) - set(EDITABLE_FIELDS)
        if unknown:
            raise TroubleshootingError(f"unknown fields: {sorted(unknown)}")
        for name in _NOT_NULL_FIELDS:
            if name in fields and not (fields[name] or "").strip():
                raise TroubleshootingError(f"{name} must not be empty")

        with self.db.cursor() as cur:
            current = self._load_detail(cur, article_id)
            if current is None:
                raise TroubleshootingError(
                    f"troubleshooting article id={article_id} does not exist"
                )
            if tag_ids is not None:
                self._assert_tags_exist(cur, tag_ids)

            set_clauses: List[str] = []
            set_params: List = []
            for name in EDITABLE_FIELDS:
                if name in fields:
                    set_clauses.append(f"{name} = %s")
                    set_params.append(fields[name])

            # embedding 元フィールドが変わったら再計算する（トランザクション外で呼びたいが、
            # 対象は最大65件・編集頻度も低いため同期実行で十分, Open Issue #2）。
            if any(name in fields for name in _EMBEDDING_SOURCE_FIELDS):
                merged = {
                    name: fields.get(name, getattr(current, name))
                    for name in _EMBEDDING_SOURCE_FIELDS
                }
                text = build_embedding_text(
                    merged["title"],
                    merged["subtitle"],
                    merged["symptom"],
                    merged["cause"],
                    merged["guidance"],
                )
                set_clauses.append("embedding = %s")
                set_params.append(to_vector_str(self.embed_fn(text)))

            if set_clauses:
                set_clauses.append("updated_at = now()")
                cur.execute(
                    f"UPDATE troubleshooting_article SET {', '.join(set_clauses)} WHERE id = %s",
                    set_params + [article_id],
                )

            if tag_ids is not None:
                cur.execute(
                    "DELETE FROM troubleshooting_article_tag WHERE article_id = %s",
                    (article_id,),
                )
                if tag_ids:
                    cur.executemany(
                        "INSERT INTO troubleshooting_article_tag (article_id, tag_id) "
                        "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        [(article_id, tid) for tid in tag_ids],
                    )

            detail = self._load_detail(cur, article_id)
        return detail

    # ------------------------------------------------------------------ #
    # 内部ヘルパ
    # ------------------------------------------------------------------ #
    def _load_detail(self, cur, article_id: int) -> Optional[TroubleshootingDetail]:
        cur.execute(
            """
            SELECT
                id, source_key, title, subtitle, symptom, operation_history,
                error_code, error_message, system_environment, hardware_environment,
                version_info, guidance, cause, notes, keyword_raw, body_html,
                source_updated_at, created_at, updated_at
            FROM troubleshooting_article
            WHERE id = %s
            """,
            (article_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None

        cur.execute(
            """
            SELECT tag.id, tag.name
            FROM troubleshooting_article_tag
            JOIN tag ON tag.id = troubleshooting_article_tag.tag_id
            WHERE troubleshooting_article_tag.article_id = %s
            ORDER BY tag.name
            """,
            (article_id,),
        )
        tags = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]

        return TroubleshootingDetail(
            id=row[0],
            source_key=row[1],
            title=row[2] or "",
            subtitle=row[3],
            symptom=row[4],
            operation_history=row[5],
            error_code=row[6],
            error_message=row[7],
            system_environment=row[8],
            hardware_environment=row[9],
            version_info=row[10],
            guidance=row[11] or "",
            cause=row[12],
            notes=row[13],
            keyword_raw=row[14],
            body_html=row[15] or "",
            source_updated_at=row[16],
            created_at=row[17],
            updated_at=row[18],
            tags=tags,
        )

    @staticmethod
    def _assert_tags_exist(cur, tag_ids: Optional[List[int]]) -> None:
        if not tag_ids:
            return
        cur.execute("SELECT id FROM tag WHERE id = ANY(%s)", (list(tag_ids),))
        found = {r[0] for r in cur.fetchall()}
        missing = [tid for tid in tag_ids if tid not in found]
        if missing:
            raise TroubleshootingError(f"tag ids do not exist: {missing}")
