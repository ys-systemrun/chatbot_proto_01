"""検証機能（質問→タグ→情報源）の API レスポンス生成ロジック（IMPL-202608260909 T9）。

質問 CRUD・検証実行（select_tags → search_knowledge のオーケストレーション）・評価保存を担う。
検証実行の失敗（業務エラー・基盤エラーいずれも）は run_question() 内でローカルに捕捉し、
verification_run へ status="error" として記録した上で 200 系で返す。app.py の
@app.exception_handler(KnowledgeMcpError)（409）は経由させない（0章 / 10章）。

CSV 一括インポート（IMPL-202608261022 T14 / ADR-0054）も本 Controller に含める。Knowledge MCP は
経由せず、VerificationDB.bulk_create_questions を直接呼び出す。
"""

from __future__ import annotations

import csv
import io
import time

from fastapi import HTTPException
from pydantic import BaseModel

from src.log import log_admin_operation
from src.mcp_client import KnowledgeMcpClient, TagSelectorMcpClient
from src.main import config
from src.verification_db import (
    VerificationDB,
    VerificationRunRecord,
    VerificationSourceRecord,
    VerificationTagRecord,
)

_tag_selector_client = TagSelectorMcpClient(config.TAG_SELECTOR_MCP_URL)
_knowledge_client = KnowledgeMcpClient(config.KNOWLEDGE_MCP_URL)


# --------------------------------------------------------------------------- #
# Pydantic モデル（5.4 節）
# --------------------------------------------------------------------------- #
class VerificationTagOut(BaseModel):
    rank_no: int
    tag_id: int | None
    tag_name: str
    score: float | None
    path: list[str] = []


class VerificationSourceOut(BaseModel):
    rank_no: int
    source_id: str | None
    source_type: str | None
    title: str | None
    content: str | None
    score: float | None
    metadata: dict = {}


class VerificationRunOut(BaseModel):
    id: int
    executed_at: str
    status: str                       # "success" | "error"
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
    existing_tags_snapshot: list[str] = []  # IMPL-202608261510 T4
    tags: list[VerificationTagOut] = []
    sources: list[VerificationSourceOut] = []


class VerificationQuestionSummary(BaseModel):
    id: int
    question_text: str
    memo: str | None
    existing_tags: list[str] = []  # IMPL-202608261510 T4
    created_at: str
    latest_run: VerificationRunOut | None


class VerificationQuestionListResponse(BaseModel):
    items: list[VerificationQuestionSummary]
    total: int


class VerificationQuestionDetail(BaseModel):
    id: int
    question_text: str
    memo: str | None
    existing_tags: list[str] = []  # IMPL-202608261510 T4
    created_at: str
    updated_at: str
    runs: list[VerificationRunOut]


class VerificationQuestionCreateRequest(BaseModel):
    question_text: str
    memo: str | None = None
    existing_tags: list[str] = []  # IMPL-202608261510 T4


class VerificationQuestionUpdateRequest(BaseModel):
    question_text: str | None = None
    memo: str | None = None
    existing_tags: list[str] | None = None  # IMPL-202608261510 T4（Noneは変更なし、0章）


class VerificationEvaluationRequest(BaseModel):
    evaluation: int          # 1=適切 / 0=不適切
    comment: str | None = None


# 一括インポート（IMPL-202608261022 T14）
class VerificationImportRowResult(BaseModel):
    row: int
    status: str
    id: int | None = None
    error: str | None = None


class VerificationImportResponse(BaseModel):
    total: int
    success_count: int
    results: list[VerificationImportRowResult]


# --------------------------------------------------------------------------- #
# レコード → Pydantic 変換
# --------------------------------------------------------------------------- #
def _to_run_out(run: VerificationRunRecord) -> VerificationRunOut:
    return VerificationRunOut(
        id=run.id,
        executed_at=run.executed_at,
        status=run.status,
        error_message=run.error_message,
        max_tags=run.max_tags,
        confidence_threshold=run.confidence_threshold,
        top_k=run.top_k,
        min_score=run.min_score,
        tag_selector_latency_ms=run.tag_selector_latency_ms,
        knowledge_mcp_latency_ms=run.knowledge_mcp_latency_ms,
        evaluation=run.evaluation,
        evaluation_comment=run.evaluation_comment,
        evaluated_at=run.evaluated_at,
        existing_tags_snapshot=run.existing_tags_snapshot,  # IMPL-202608261510 T4
        tags=[
            VerificationTagOut(
                rank_no=t.rank_no,
                tag_id=t.tag_id,
                tag_name=t.tag_name,
                score=t.score,
                path=t.path,
            )
            for t in run.tags
        ],
        sources=[
            VerificationSourceOut(
                rank_no=s.rank_no,
                source_id=s.source_id,
                source_type=s.source_type,
                title=s.title,
                content=s.content,
                score=s.score,
                metadata=s.metadata,
            )
            for s in run.sources
        ],
    )


def _to_summary(record) -> VerificationQuestionSummary:
    return VerificationQuestionSummary(
        id=record.id,
        question_text=record.question_text,
        memo=record.memo,
        existing_tags=record.existing_tags,  # IMPL-202608261510 T4
        created_at=record.created_at,
        latest_run=_to_run_out(record.latest_run) if record.latest_run else None,
    )


# --------------------------------------------------------------------------- #
# 質問 CRUD（薄い層: VerificationDB を呼んで Pydantic へ変換するだけ）
# --------------------------------------------------------------------------- #
def list_questions(
    keyword: str | None, limit: int, offset: int
) -> VerificationQuestionListResponse:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    with VerificationDB(config.CONVERSATION_DB_URL) as db:
        records, total = db.list_questions(keyword, limit, offset)
    return VerificationQuestionListResponse(
        items=[_to_summary(r) for r in records], total=total
    )


def create_question(
    body: VerificationQuestionCreateRequest,
) -> VerificationQuestionSummary:
    if not body.question_text or not body.question_text.strip():
        raise HTTPException(status_code=422, detail="question_text is required")
    with VerificationDB(config.CONVERSATION_DB_URL) as db:
        record = db.create_question(body.question_text, body.memo, body.existing_tags)  # IMPL-202608261510 T4
    log_admin_operation("create", "verification_question", record.id, body.model_dump())
    return _to_summary(record)


def get_question_detail(question_id: int) -> VerificationQuestionDetail:
    with VerificationDB(config.CONVERSATION_DB_URL) as db:
        record = db.get_question_detail(question_id)
    if record is None:
        raise HTTPException(status_code=404, detail="verification question not found")
    return VerificationQuestionDetail(
        id=record.id,
        question_text=record.question_text,
        memo=record.memo,
        existing_tags=record.existing_tags,  # IMPL-202608261510 T4
        created_at=record.created_at,
        updated_at=record.updated_at,
        runs=[_to_run_out(r) for r in record.runs],
    )


def update_question(
    question_id: int, body: VerificationQuestionUpdateRequest
) -> VerificationQuestionSummary:
    with VerificationDB(config.CONVERSATION_DB_URL) as db:
        record = db.update_question(
            question_id, body.question_text, body.memo, body.existing_tags  # IMPL-202608261510 T4
        )
    if record is None:
        raise HTTPException(status_code=404, detail="verification question not found")
    log_admin_operation(
        "update", "verification_question", question_id, body.model_dump(exclude_unset=True)
    )
    return _to_summary(record)


def delete_question(question_id: int) -> None:
    with VerificationDB(config.CONVERSATION_DB_URL) as db:
        deleted = db.delete_question(question_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="verification question not found")
    log_admin_operation("delete", "verification_question", question_id)


def save_evaluation(
    run_id: int, body: VerificationEvaluationRequest
) -> VerificationRunOut:
    with VerificationDB(config.CONVERSATION_DB_URL) as db:
        run = db.save_evaluation(run_id, body.evaluation, body.comment)
    if run is None:
        raise HTTPException(status_code=404, detail="verification run not found")
    log_admin_operation(
        "update", "verification_run", run_id, body.model_dump()
    )
    return _to_run_out(run)


# --------------------------------------------------------------------------- #
# 検証実行オーケストレーション（要件定義書6.3節 / 5.4節）
# --------------------------------------------------------------------------- #
async def run_question(question_id: int) -> VerificationRunOut:
    with VerificationDB(config.CONVERSATION_DB_URL) as db:
        question = db.get_question(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="verification question not found")

    max_tags = config.VERIFICATION_MAX_TAGS
    confidence_threshold = config.VERIFICATION_CONFIDENCE_THRESHOLD
    top_k = config.VERIFICATION_TOP_K
    min_score = config.VERIFICATION_MIN_SCORE
    snapshot = question.question_text
    existing_tags = list(question.existing_tags or [])  # IMPL-202608261510 T4

    # --- select_tags -------------------------------------------------------- #
    t0 = time.monotonic()
    try:
        tags_result = await _tag_selector_client.call_tool(
            "select_tags",
            {
                "query": question.question_text,
                "max_tags": max_tags,
                "confidence_threshold": confidence_threshold,
            },
        )
        tag_selector_latency_ms = int((time.monotonic() - t0) * 1000)
    except Exception as e:  # noqa: BLE001 - 検証結果として一貫して扱う（0章）
        with VerificationDB(config.CONVERSATION_DB_URL) as db:
            run = db.create_run(
                question_id,
                snapshot,
                status="error",
                error_message=f"select_tags failed: {e}",
                max_tags=max_tags,
                confidence_threshold=confidence_threshold,
                top_k=None,
                min_score=None,
                tag_selector_latency_ms=int((time.monotonic() - t0) * 1000),
                knowledge_mcp_latency_ms=None,
                existing_tags_snapshot=existing_tags,  # IMPL-202608261510 T4
                tags=[],
                sources=[],
            )
        return _to_run_out(run)

    # --- 新規タグの特定（既存タグに含まれないもの, IMPL-202608261510 T4 / ADR-0060） ------- #
    existing_set = set(existing_tags)
    new_selected = [
        t for t in tags_result.get("selected", []) if t["name"] not in existing_set
    ]
    tags = [
        VerificationTagRecord(
            rank_no=i + 1,  # 新規タグに絞った後の連番（0章）
            tag_id=t.get("id"),
            tag_name=t["name"],
            score=t.get("score"),
            path=t.get("path", []),
        )
        for i, t in enumerate(new_selected)
    ]

    # --- search_knowledge: 既存タグ＋新規タグを1回で渡す（ADR-0060、4章の前提に注意） ------ #
    merged_tag_names = list(dict.fromkeys(existing_tags + [t.tag_name for t in tags]))
    t1 = time.monotonic()
    try:
        search_result = await _knowledge_client.call_tool(
            "search_knowledge",
            {
                "query": question.question_text,
                "tags": merged_tag_names,
                "top_k": top_k,
                "min_score": min_score,
            },
        )
        knowledge_mcp_latency_ms = int((time.monotonic() - t1) * 1000)
    except Exception as e:  # noqa: BLE001 - 検証結果として一貫して扱う（0章）
        with VerificationDB(config.CONVERSATION_DB_URL) as db:
            run = db.create_run(
                question_id,
                snapshot,
                status="error",
                error_message=f"search_knowledge failed: {e}",
                max_tags=max_tags,
                confidence_threshold=confidence_threshold,
                top_k=top_k,
                min_score=min_score,
                tag_selector_latency_ms=tag_selector_latency_ms,
                knowledge_mcp_latency_ms=int((time.monotonic() - t1) * 1000),
                existing_tags_snapshot=existing_tags,  # IMPL-202608261510 T4
                tags=tags,
                sources=[],
            )
        return _to_run_out(run)

    sources = [
        VerificationSourceRecord(
            rank_no=i + 1,
            source_id=r.get("id"),
            source_type=r.get("source_type"),
            title=r.get("title"),
            content=r.get("content"),
            score=r.get("score"),
            metadata=r.get("metadata", {}),
        )
        for i, r in enumerate(search_result.get("results", []))
    ]

    with VerificationDB(config.CONVERSATION_DB_URL) as db:
        run = db.create_run(
            question_id,
            snapshot,
            status="success",
            error_message=None,
            max_tags=max_tags,
            confidence_threshold=confidence_threshold,
            top_k=top_k,
            min_score=min_score,
            tag_selector_latency_ms=tag_selector_latency_ms,
            knowledge_mcp_latency_ms=knowledge_mcp_latency_ms,
            existing_tags_snapshot=existing_tags,  # IMPL-202608261510 T4
            tags=tags,
            sources=sources,
        )
    return _to_run_out(run)


# --------------------------------------------------------------------------- #
# CSV 一括インポート（IMPL-202608261022 T14 / ADR-0054）
# --------------------------------------------------------------------------- #
def _parse_verification_import_csv(csv_bytes: bytes) -> list[dict]:
    """CSV（UTF-8, BOM可）をパースして [{"question_text", "memo"}, ...] を返す。

    列の機械的なバリデーション（question_text 列の存在）のみをここで行い、
    空行スキップ・重複判定等の業務ロジックは VerificationDB.bulk_create_questions に委ねる。
    """
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=422,
            detail="CSV は UTF-8（BOM 付き可）で保存してください。",
        )
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "question_text" not in reader.fieldnames:
        raise HTTPException(
            status_code=422,
            detail="CSV に question_text 列が必要です（任意で memo 列）。",
        )
    rows: list[dict] = []
    for raw in reader:
        rows.append(
            {
                "question_text": (raw.get("question_text") or "").strip(),
                "memo": (raw.get("memo") or "").strip() or None,
            }
        )
    return rows


def import_questions_csv(csv_bytes: bytes) -> VerificationImportResponse:
    rows = _parse_verification_import_csv(csv_bytes)
    with VerificationDB(config.CONVERSATION_DB_URL) as db:
        results = db.bulk_create_questions(rows)
    log_admin_operation(
        "import", "verification_question", None, {"total": len(results)}
    )
    return VerificationImportResponse(
        total=len(results),
        success_count=sum(1 for r in results if r["status"] == "success"),
        results=[VerificationImportRowResult(**r) for r in results],
    )
