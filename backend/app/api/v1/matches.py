"""匹配与候选披露接口。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, Path, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_batch, require_non_admin
from app.core.batch_status import is_readable_terminal, status_message
from app.core.config import settings
from app.core.logging import request_id_var
from app.core.response import (
    BusinessError,
    ConflictError,
    GoneError,
    NotFoundError,
    ValidationError,
)
from app.core.timeutil import utcnow
from app.db.enums import BatchStatus, CandidateStatus, DisclosureLevel, ItemLifecycleStatus
from app.db.models import MatchBatch, MatchRecord, User
from app.db.session import get_db
from app.schemas.match import (
    CandidateSummaryListOut,
    ExplanationOut,
    FeedbackOut,
    FeedbackRequest,
    MatchAcceptedOut,
    MatchBatchOut,
    MatchCreateRequest,
    MyBatchItem,
    MyBatchListOut,
)
from app.services import (
    audit,
    disclosure_policy,
    disclosure_service,
    lifecycle,
    match_orchestrator,
    rate_limit,
    security_service,
)
from app.services.item_service import get_item

router = APIRouter(prefix="/matches", tags=["matches"])


def _request_id() -> str:
    return request_id_var.get() or "unknown"


def _batch_out(batch: MatchBatch) -> MatchBatchOut:
    message = status_message(batch.status)
    return MatchBatchOut(
        batch_id=batch.batch_id,
        initiated_item_type=batch.initiated_item_type,
        initiated_item_id=batch.initiated_item_id,
        status=batch.status,
        candidate_count=batch.candidate_count,
        degraded=batch.degraded,
        degraded_reason=batch.degraded_reason,
        recall_channel=batch.recall_channel,
        threshold=float(batch.threshold),
        quota=int(batch.quota),
        algorithm_version=batch.algorithm_version,
        config_version=batch.config_version,
        created_at=batch.created_at,
        completed_at=batch.completed_at,
        expires_at=batch.expires_at,
        message=message,
    )


def _assert_readable(db: Session, batch: MatchBatch) -> None:
    if getattr(batch, "batch_kind", "formal") == "preview":
        raise NotFoundError("匹配结果不存在")
    if batch.status in {
        BatchStatus.invalidated.value,
        BatchStatus.expired.value,
        BatchStatus.archived.value,
    }:
        raise GoneError("匹配结果已过期或已失效，请重新匹配")
    if batch.status == BatchStatus.processing.value:
        return
    if not batch.visible:
        raise NotFoundError("匹配结果不存在")
    now = utcnow()
    if batch.expires_at is None or batch.expires_at <= now:
        batch.status = BatchStatus.expired.value
        db.commit()
        raise GoneError("匹配结果已过期，请重新匹配")
    if not is_readable_terminal(batch.status):
        raise GoneError("匹配结果不可用，请重新匹配")
    initiated = get_item(db, batch.initiated_item_type, batch.initiated_item_id)
    if initiated.status != ItemLifecycleStatus.active.value or initiated.is_removed:
        raise GoneError("匹配结果已随记录状态变化失效，请重新匹配")


def _candidate_rows(db: Session, batch: MatchBatch) -> list[MatchRecord]:
    return list(
        db.execute(
            select(MatchRecord)
            .where(
                MatchRecord.batch_id == batch.batch_id,
                MatchRecord.candidate_status == CandidateStatus.valid.value,
            )
            .order_by(MatchRecord.score.desc(), MatchRecord.id.asc())
        ).scalars().all()
    )


@router.post("", response_model=MatchAcceptedOut, status_code=202)
def create_match(
    payload: MatchCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
) -> MatchAcceptedOut:
    batch, reused = match_orchestrator.accept_match(
        db,
        user=user,
        lost_item_id=payload.lost_item_id,
        found_item_id=payload.found_item_id,
    )
    if reused:
        response.status_code = 200
    return MatchAcceptedOut(
        batch_id=batch.batch_id,
        status=batch.status,
        reused=reused,
        accepted_at=batch.created_at,
    )


@router.get("/my", response_model=MyBatchListOut)
def my_batches(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
) -> MyBatchListOut:
    stmt = select(MatchBatch).where(MatchBatch.initiator_id == user.id)
    if status:
        stmt = stmt.where(MatchBatch.status == status)
    rows = db.execute(stmt.order_by(MatchBatch.created_at.desc())).scalars().all()
    items: list[MyBatchItem] = []
    for batch in rows:
        item = get_item(db, batch.initiated_item_type, batch.initiated_item_id)
        items.append(
            MyBatchItem(
                batch_id=batch.batch_id,
                initiated_item_id=batch.initiated_item_id,
                initiated_item_type=batch.initiated_item_type,
                status=batch.status,
                candidate_count=batch.candidate_count,
                degraded=batch.degraded,
                created_at=batch.created_at,
                expires_at=batch.expires_at,
                can_rematch=item.status == ItemLifecycleStatus.active.value,
            )
        )
    total = len(items)
    start = (page - 1) * page_size
    return MyBatchListOut(items=items[start : start + page_size], total=total)


@router.get("/batches/{batch_id}", response_model=MatchBatchOut)
def batch_detail(
    db: Session = Depends(get_db),
    batch: MatchBatch = Depends(get_owned_batch),
) -> MatchBatchOut:
    _assert_readable(db, batch)
    return _batch_out(batch)


@router.get("/batches/{batch_id}/candidates", response_model=CandidateSummaryListOut)
def list_candidates(
    request: Request,
    batch: MatchBatch = Depends(get_owned_batch),
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
    category: str | None = Query(default=None),
    color: str | None = Query(default=None),
    time_from: datetime | None = Query(default=None),
    time_to: datetime | None = Query(default=None),
    area_code: str | None = Query(default=None),
    keyword: str | None = Query(default=None, max_length=50),
) -> CandidateSummaryListOut:
    _assert_readable(db, batch)
    if batch.status == BatchStatus.processing.value:
        raise ConflictError("匹配仍在处理中，请稍后刷新", code="MATCH_NOT_READY")
    if batch.status == BatchStatus.no_candidates.value:
        return CandidateSummaryListOut(batch_id=batch.batch_id)

    rate_limit.check_and_increment(
        db, subject_type="user", subject_id=user.id, action="view_candidate"
    )
    rate_limit.check_and_increment(
        db, subject_type="batch", subject_id=batch.batch_id, action="view_summary"
    )

    summaries = []
    total = 0
    for record in _candidate_rows(db, batch):
        total += 1
        if record.view_count >= settings.view_candidate_total_limit:
            continue
        candidate_type = record.candidate_item_type
        candidate_id = record.candidate_item_id
        item = get_item(db, candidate_type, candidate_id)
        summary = disclosure_service.build_summary(db, record, item, candidate_type)
        if category and summary.category != category:
            continue
        if color and (summary.color or "") != color:
            continue
        if time_from and summary.occurred_on and summary.occurred_on < time_from.date().isoformat():
            continue
        if time_to and summary.occurred_on and summary.occurred_on > time_to.date().isoformat():
            continue
        if area_code and summary.area_name != disclosure_policy.area_name(area_code):
            continue
        if keyword and keyword not in (summary.title_excerpt + summary.description_excerpt):
            continue
        summaries.append(summary)
        record.view_count += 1
        disclosure_service.log_access(
            db,
            actor_id=user.id,
            batch_id=batch.batch_id,
            candidate_public_id=record.candidate_public_id or "",
            action="view_summary",
            disclosure_level=DisclosureLevel.summary.value,
            request_id=_request_id(),
        )

    security_service.check_view_burst(db, actor_id=user.id)
    db.commit()
    return CandidateSummaryListOut(
        batch_id=batch.batch_id,
        candidates=summaries,
        filtered_total=len(summaries),
        total=total,
    )


@router.get("/batches/{batch_id}/candidates/{candidate_public_id}")
def candidate_detail(
    request: Request,
    candidate_public_id: str = Path(...),
    batch: MatchBatch = Depends(get_owned_batch),
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
):
    _assert_readable(db, batch)
    if batch.status == BatchStatus.no_candidates.value:
        raise NotFoundError("候选不存在")
    record, item, candidate_type = disclosure_service.resolve_candidate(
        db, batch_id=batch.batch_id, public_id=candidate_public_id
    )
    level = disclosure_service.resolve_level(
        db, applicant_id=user.id, record=record
    )
    if level == DisclosureLevel.handover:
        contact = disclosure_service.contact_for(
            db, applicant_id=user.id, record=record
        )
        payload = disclosure_service.build_handover(
            db, record, item, candidate_type, contact
        )
        action = "view_handover"
    elif level == DisclosureLevel.verified:
        payload = disclosure_service.build_verified(db, record, item, candidate_type)
        action = "view_summary"
    else:
        payload = disclosure_service.build_summary(db, record, item, candidate_type)
        action = "view_summary"
    record.view_count += 1
    disclosure_service.log_access(
        db,
        actor_id=user.id,
        batch_id=batch.batch_id,
        candidate_public_id=candidate_public_id,
        action=action,
        disclosure_level=level.value,
        request_id=_request_id(),
    )
    db.commit()
    return payload


@router.get("/candidates/{candidate_public_id}/explanation", response_model=ExplanationOut)
def candidate_explanation(
    request: Request,
    candidate_public_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
):
    record = disclosure_service.find_by_public_id(db, candidate_public_id)
    if record is None:
        raise NotFoundError("候选不存在")
    batch = db.execute(
        select(MatchBatch).where(MatchBatch.batch_id == record.batch_id)
    ).scalars().first()
    if batch is None or batch.initiator_id != user.id:
        raise NotFoundError("候选不存在")
    _assert_readable(db, batch)
    if batch.status == BatchStatus.no_candidates.value:
        raise NotFoundError("候选不存在")
    disclosure_service.log_access(
        db,
        actor_id=user.id,
        batch_id=batch.batch_id,
        candidate_public_id=candidate_public_id,
        action="expand_reason",
        disclosure_level=record.disclosure_level,
        request_id=_request_id(),
    )
    db.commit()
    reason = record.reason_json or {}
    return ExplanationOut(
        candidate_public_id=candidate_public_id,
        score=float(record.score),
        score_breakdown=disclosure_service._breakdown(record.score_breakdown),  # noqa: SLF001
        reasons=[str(x) for x in reason.get("reasons", [])],
        differences=disclosure_service._differences(record),  # noqa: SLF001
        explanation_status=record.explanation_status,
    )


@router.post("/candidates/{candidate_public_id}/feedback", response_model=FeedbackOut)
def candidate_feedback(
    candidate_public_id: str,
    payload: FeedbackRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
):
    record = disclosure_service.find_by_public_id(db, candidate_public_id)
    if record is None:
        raise NotFoundError("候选不存在")
    if record.initiated_by != user.id:
        raise NotFoundError("候选不存在")
    batch = db.execute(
        select(MatchBatch).where(MatchBatch.batch_id == record.batch_id)
    ).scalars().first()
    if batch is None or batch.status == BatchStatus.no_candidates.value:
        raise NotFoundError("候选不存在")
    if payload.note and disclosure_policy.sanitize_disclosure_text(payload.note) != payload.note.strip():
        raise BusinessError(
            "反馈内容不得包含联系方式", code="CONTACT_INFO_FORBIDDEN", status_code=422
        )

    from app.db.models import MatchFeedback

    existing = db.execute(
        select(MatchFeedback).where(
            MatchFeedback.candidate_public_id == candidate_public_id,
            MatchFeedback.reporter_id == user.id,
        )
    ).scalars().first()
    if existing is not None:
        response.status_code = 200
        return FeedbackOut(feedback_id=existing.id, recorded=True)

    feedback = MatchFeedback(
        candidate_public_id=candidate_public_id,
        candidate_id=record.id,
        reporter_id=user.id,
        feedback_type=payload.feedback_type,
        note=payload.note,
        created_at=utcnow(),
    )
    db.add(feedback)
    record.candidate_status = CandidateStatus.feedback_reported.value
    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="candidate_feedback",
        entity_type="match_record",
        entity_id=record.id,
        batch_id=record.batch_id,
        candidate_id=candidate_public_id,
        details={"feedback_type": payload.feedback_type},
    )
    db.commit()
    db.refresh(feedback)
    response.status_code = 201
    return FeedbackOut(feedback_id=feedback.id, recorded=True)


@router.post("/rematch", response_model=MatchAcceptedOut, status_code=202)
def rematch(
    payload: MatchCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
) -> MatchAcceptedOut:
    batch, _ = match_orchestrator.rematch(
        db,
        user=user,
        lost_item_id=payload.lost_item_id,
        found_item_id=payload.found_item_id,
    )
    return MatchAcceptedOut(
        batch_id=batch.batch_id,
        status=batch.status,
        reused=False,
        accepted_at=batch.created_at,
    )