"""上下架审核服务。

管理员只做两类审核：待上架、待下架。审核 DTO 与响应不含候选、分数、
对侧记录、申请人身份与私密核验内容。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.listing_modes import LISTING_REVIEW_RETIRED_CODE, is_auto_mode
from app.core.response import ConflictError, ForbiddenError, GoneError, NotFoundError, ValidationError
from app.core.timeutil import utcnow
from app.db.enums import (
    BatchStatus,
    ItemLifecycleStatus as S,
    ItemType,
    ReviewTicketStatus,
    ReviewType,
    UserRole,
)
from app.db.models import MatchBatch, MatchRecord, ReviewTicket, User
from app.schemas.admin import (
    ComplianceCheckOut,
    ReviewDecisionOut,
    ReviewHistoryItem,
    ReviewQueueItem,
    ReviewQueueOut,
    ReviewTicketDetailOut,
)
from app.services import audit, notification_service
from app.services.item_service import _model, _TIME_FIELD, get_item  # noqa: PLC2701
from app.services.state_machine import assert_transition
from app.services.visibility_policy import assert_can_review

_STATUS_LABEL = {
    S.pending_listing.value: "待上架审核",
    S.active.value: "已上架",
    S.listing_rejected.value: "上架驳回",
    S.delisting_review.value: "下架审核中",
    S.delisted.value: "已下架",
    S.claimed.value: "已认领",
    S.resolved.value: "已完成",
    S.closed.value: "已关闭",
}


def _ticket_no(db: Session, review_type: str) -> str:
    prefix = "LT" if review_type == ReviewType.listing.value else "DT"
    base = utcnow().strftime("%Y%m%d")
    for _ in range(5):
        seq = db.execute(select(func.count(ReviewTicket.id))).scalar_one() + 1
        candidate = f"{prefix}{base}-{seq:04d}"
        exists = db.execute(
            select(ReviewTicket.id).where(ReviewTicket.ticket_no == candidate)
        ).scalar_one_or_none()
        if exists is None:
            return candidate
    return f"{prefix}{base}-{uuid.uuid4().hex[:6].upper()}"


def create_ticket(
    db: Session,
    *,
    review_type: str,
    item_type: str,
    item_id: int,
    applicant_id: int | None,
    review_round: int,
    source: str = "owner_request",
    status: str = ReviewTicketStatus.pending.value,
    opinion: str | None = None,
    decided_at: datetime | None = None,
) -> ReviewTicket:
    now = utcnow()
    pending = status == ReviewTicketStatus.pending.value
    ticket = ReviewTicket(
        ticket_no=_ticket_no(db, review_type),
        review_type=review_type,
        source=source,
        item_type=item_type,
        item_id=item_id,
        applicant_id=applicant_id,
        review_round=review_round,
        status=status,
        opinion=opinion,
        decided_by=None,
        decided_at=decided_at,
        deadline_at=(now + timedelta(hours=24)) if pending else None,
        created_at=now,
    )
    db.add(ticket)
    db.flush()
    return ticket


def list_tickets(
    db: Session,
    *,
    review_type: str | None,
    source: str | None,
    overdue: bool | None,
    page: int,
    page_size: int,
    history: bool = False,
) -> ReviewQueueOut:
    stmt = select(ReviewTicket)
    if history:
        stmt = stmt.where(
            ReviewTicket.status != ReviewTicketStatus.pending.value
        ).order_by(ReviewTicket.decided_at.desc())
    else:
        stmt = stmt.where(
            ReviewTicket.status == ReviewTicketStatus.pending.value
        ).order_by(ReviewTicket.created_at.asc())
    if review_type:
        stmt = stmt.where(ReviewTicket.review_type == review_type)
    if source:
        stmt = stmt.where(ReviewTicket.source == source)
    rows = db.execute(stmt).scalars().all()
    now = utcnow()
    items: list[ReviewQueueItem] = []
    for ticket in rows:
        waiting = int((now - ticket.created_at).total_seconds() // 60)
        is_overdue = bool(ticket.deadline_at and now > ticket.deadline_at)
        if overdue is True and not is_overdue:
            continue
        if overdue is False and is_overdue:
            continue
        model = _model(ticket.item_type)
        item = db.get(model, ticket.item_id)
        items.append(
            ReviewQueueItem(
                ticket_no=ticket.ticket_no,
                review_type=ticket.review_type,
                source=ticket.source,
                item_type=ticket.item_type,
                item_id=ticket.item_id,
                item_title=item.title if item else "（记录已不存在）",
                status=ticket.status,
                waiting_minutes=waiting,
                overdue=is_overdue,
                created_at=ticket.created_at,
            )
        )
    total = len(items)
    start = (page - 1) * page_size
    return ReviewQueueOut(items=items[start : start + page_size], total=total)


def get_ticket(db: Session, ticket_no: str) -> ReviewTicketDetailOut:
    ticket = db.execute(
        select(ReviewTicket).where(ReviewTicket.ticket_no == ticket_no)
    ).scalars().first()
    if ticket is None:
        raise NotFoundError("审核单不存在")
    item = get_item(db, ticket.item_type, ticket.item_id)
    if ticket.status == ReviewTicketStatus.pending.value:
        assert_can_review(status=item.status)

    checks = [
        ComplianceCheckOut(
            key="has_category", passed=bool(item.category), note=None
        ),
        ComplianceCheckOut(
            key="has_location", passed=bool(item.location_text), note="地点为必填"
        ),
        ComplianceCheckOut(
            key="info_sufficient",
            passed=bool(item.info_sufficient),
            note=None if item.info_sufficient else "图片或文字信息不足",
        ),
        ComplianceCheckOut(
            key="no_contact_in_text",
            passed=True,
            note="审核页不展示私密核验与联系方式",
        ),
    ]
    history = [
        ReviewHistoryItem(
            review_round=row.review_round,
            status=row.status,
            opinion=row.opinion,
            decided_at=row.decided_at,
        )
        for row in db.execute(
            select(ReviewTicket)
            .where(
                ReviewTicket.item_type == ticket.item_type,
                ReviewTicket.item_id == ticket.item_id,
            )
            .order_by(ReviewTicket.created_at.asc())
        ).scalars().all()
    ]
    images = []
    from app.services.item_service import serialize_images

    images = serialize_images(list(getattr(item, "images", []) or []))

    return ReviewTicketDetailOut(
        ticket_no=ticket.ticket_no,
        review_type=ticket.review_type,
        source=ticket.source,
        status=ticket.status,
        item_type=ticket.item_type,
        item_id=ticket.item_id,
        item_title=item.title,
        item_category=item.category,
        item_description=item.description,
        location_text=item.location_text,
        occurred_at=getattr(item, _TIME_FIELD[ticket.item_type]),
        images=images,
        compliance_checks=checks,
        history=history,
    )


def decide(
    db: Session,
    *,
    admin: User,
    ticket_no: str,
    decision: str,
    opinion: str | None,
) -> ReviewDecisionOut:
    if admin.role != UserRole.admin.value:
        raise ForbiddenError("需要管理员权限")
    ticket = db.execute(
        select(ReviewTicket).where(ReviewTicket.ticket_no == ticket_no)
    ).scalars().first()
    if ticket is None:
        raise NotFoundError("审核单不存在")
    if ticket.review_type == ReviewType.listing.value and is_auto_mode():
        raise GoneError(
            "上架审核已退役，记录已由系统自动完成上架",
            code=LISTING_REVIEW_RETIRED_CODE,
        )
    if ticket.status != ReviewTicketStatus.pending.value:
        raise ConflictError("该审核单已被处理", code="TICKET_ALREADY_DECIDED")

    item = get_item(db, ticket.item_type, ticket.item_id)
    assert_can_review(status=item.status)
    if item.user_id == admin.id:
        raise ForbiddenError("不得审核本人提交的记录", code="SELF_REVIEW_FORBIDDEN")

    before = item.status
    match_task_created = False
    impact: dict = {}

    if ticket.review_type == ReviewType.listing.value:
        if item.status != S.pending_listing.value:
            raise ConflictError("记录状态已变化，请刷新后重试", code="ITEM_STATE_CHANGED")
        if decision == "approve":
            assert_transition(before, S.active.value)
            item.status = S.active.value
            item.visibility_scope = "match_disclosure"
            item.delist_reason = None
            if item.info_sufficient:
                from app.services.match_orchestrator import enqueue_auto_match

                batch = enqueue_auto_match(
                    db,
                    item_type=ticket.item_type,
                    item=item,
                    initiator_id=item.user_id,
                )
                match_task_created = batch is not None
                impact["batch_id"] = batch.batch_id if batch else None
        else:
            assert_transition(before, S.listing_rejected.value)
            item.status = S.listing_rejected.value
            item.delist_reason = opinion
    else:
        if item.status != S.delisting_review.value:
            raise ConflictError("记录状态已变化，请刷新后重试", code="ITEM_STATE_CHANGED")
        if decision == "approve":
            assert_transition(before, S.delisted.value)
            item.status = S.delisted.value
            item.is_removed = True
            item.delisted_at = utcnow()
            impact["invalidated_batches"] = invalidate_item_batches(
                db, ticket.item_type, ticket.item_id
            )
        else:
            assert_transition(before, S.active.value)
            item.status = S.active.value
            item.is_removed = False

    ticket.status = (
        ReviewTicketStatus.approved.value
        if decision == "approve"
        else ReviewTicketStatus.rejected.value
    )
    ticket.opinion = opinion
    ticket.decided_by = admin.id
    ticket.decided_at = utcnow()

    audit.record_audit(
        db,
        actor_id=admin.id,
        actor_role=admin.role,
        action=f"review_{ticket.review_type}_{decision}",
        entity_type="review_ticket",
        entity_id=ticket.id,
        before_status=before,
        after_status=item.status,
        reason=opinion,
        details={"ticket_no": ticket.ticket_no, "item_type": ticket.item_type},
    )
    notification_service.notify(
        db,
        user_id=item.user_id,
        event_type="review_result",
        ref_type="review_ticket",
        ref_id=ticket.id,
    )
    db.commit()
    db.refresh(ticket)

    return ReviewDecisionOut(
        ticket_no=ticket.ticket_no,
        status=ticket.status,
        item_status=item.status,
        decided_at=ticket.decided_at or utcnow(),
        match_task_created=match_task_created,
        impact=impact,
    )


def apply_delist(
    db: Session, *, user: User, item_type: str, item_id: int, reason: str
) -> ReviewTicket:
    item = get_item(db, item_type, item_id)
    if item.user_id != user.id:
        raise NotFoundError("记录不存在")
    if item.status not in {S.active.value, S.claimed.value}:
        raise ConflictError("记录当前状态不允许申请下架", code="ITEM_NOT_EDITABLE")
    assert_transition(item.status, S.delisting_review.value)
    before = item.status
    item.status = S.delisting_review.value
    item.delist_reason = reason
    ticket = create_ticket(
        db,
        review_type=ReviewType.delisting.value,
        item_type=item_type,
        item_id=item_id,
        applicant_id=user.id,
        review_round=item.review_round,
        source="owner_request",
    )
    item.latest_ticket_id = ticket.id
    invalidate_item_batches(db, item_type, item_id)
    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="delist_requested",
        entity_type=f"{item_type}_item",
        entity_id=item_id,
        before_status=before,
        after_status=item.status,
        reason=reason,
        details={"ticket_no": ticket.ticket_no},
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def invalidate_item_batches(db: Session, item_type: str, item_id: int) -> int:
    """把与该记录相关的完成批次置为 invalidated，候选同步失效。"""
    batches = db.execute(
        select(MatchBatch).where(
            MatchBatch.initiated_item_type == item_type,
            MatchBatch.initiated_item_id == item_id,
            MatchBatch.status.in_(
                [
                    BatchStatus.processing.value,
                    BatchStatus.completed.value,
                    BatchStatus.degraded_completed.value,
                    BatchStatus.no_candidates.value,
                ]
            ),
        )
    ).scalars().all()
    for batch in batches:
        batch.status = BatchStatus.invalidated.value
    if batches:
        db.execute(
            update(MatchRecord)
            .where(MatchRecord.batch_id.in_([b.batch_id for b in batches]))
            .values(candidate_status="invalidated")
        )
    return len(batches)