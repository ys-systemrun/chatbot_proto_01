"""検証機能の永続化モデル（IMPL-202608260909 T6、ADR-0048）。

既存 conversation_db/models.py と同様、dataclass で定義する。
conversation データベース（CONVERSATION_DB_URL）の verification_* 4テーブルに対応する。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VerificationTagRecord:
    rank_no: int
    tag_name: str
    tag_id: int | None = None
    score: float | None = None
    path: list[str] = field(default_factory=list)


@dataclass
class VerificationSourceRecord:
    rank_no: int
    source_id: str | None = None
    source_type: str | None = None
    title: str | None = None
    content: str | None = None
    score: float | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class VerificationRunRecord:
    id: int
    question_id: int
    executed_at: str
    status: str
    error_message: str | None
    max_tags: int | None
    confidence_threshold: float | None
    top_k: int | None
    min_score: float | None
    tag_selector_latency_ms: int | None
    knowledge_mcp_latency_ms: int | None
    evaluation: int | None
    evaluation_comment: str | None
    evaluated_at: str | None
    existing_tags_snapshot: list[str] = field(default_factory=list)  # IMPL-202608261510 T2
    tags: list[VerificationTagRecord] = field(default_factory=list)
    sources: list[VerificationSourceRecord] = field(default_factory=list)


@dataclass
class VerificationQuestionRecord:
    id: int
    question_text: str
    memo: str | None
    created_at: str
    updated_at: str
    existing_tags: list[str] = field(default_factory=list)  # IMPL-202608261510 T2
    latest_run: VerificationRunRecord | None = None
    runs: list[VerificationRunRecord] = field(default_factory=list)
