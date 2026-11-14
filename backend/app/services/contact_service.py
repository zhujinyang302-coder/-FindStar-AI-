"""双向申请闭环：认领申请与归还线索。

确认主体是对侧记录发布者；管理员不参与。申请与记录状态在同一事务内联动。
"""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.response import (
    BusinessError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
)
from app.core.timeutil import utcnow
from app.db.enums import (
    BatchStatus,
    CandidateStatus,
    ContactStatus,
    ContactType,
    DisclosureLevel,
    ItemLifecycleStatus as S,
    ItemType,
    SENSITIVE_CATEGORIES,
)
from app.db.models import ContactRequest, MatchBatch, MatchRecord, User
from app.schemas.contact import (
    ContactCreateRequest,
    ContactConfirmOut,
    ContactConfirmRequest,
    ContactRejectRequest,
    ContactRequestDetailOut,
    ContactRequestListItem,
    ContactRequestListOut,
    ContactRequestOut,
    ReceivedContactItem,
    ReceivedContactListOut,
)
from app.services import audit, disclosure_service, notification_service, rate_limit
from app.services.item_service import get_item
from app.services.state_machine import assert_transition

_CONTACT_PATTERN = re.compile(
    r"1[3-9]\d{9}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
    r"(?:QQ|微信|wx|wechat|VX|vx)\s*[:：]?\s*[A-Za-z0-9_-]{5,}",
    re.IGNORECASE,
)


def _has_contact_info(text: str) -> bool:
    return bool(_CONTACT_PATTERN.search(text or ""))


def _lock_key(applicant_id: int, target_type: str, target_id: int) -> str:
    raw = f"{applicant_id}|{target_type}|{target_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def submit(
    db: Session, *, user: User, payload: ContactCreateRequest
) -> tuple[ContactRequest, bool]:
    batch = db.execute(
        select(MatchBatch).where(
            MatchBatch.batch_id == payload.batch_id,
            MatchBatch.initiator_id == user.id,
        )
    ).scalars().first()
    if batch is None:
        raise NotFoundError("匹配批次不存在")
    if batch.status != BatchStatus.processing.value and batch.status not in {
        BatchStatus.completed.value,
        BatchStatus.degraded_completed.value,
    }:
        raise ConflictError("匹配结果已失效", code="CANDIDATE_INVALID")

    record, item, candidate_type = disclosure_service.resolve_candidate(
        db, batch_id=batch.batch_id, public_id=payload.candidate_public_id
    )
    if record.candidate_status != CandidateStatus.valid.value:
        raise ConflictError("候选已失效", code="CANDIDATE_INVALID")
    if item.user_id == user.id:
        raise ForbiddenError("不能对自己发布的记录提交申请", code="SELF_REQUEST_FORBIDDEN")

    expected = (
        ContactType.claim.value
        if batch.initiated_item_type == ItemType.lost.value
        else ContactType.return_clue.value
    )
    if payload.request_type != expected:
        raise ConflictError("申请类型与匹配方向不一致", code="REQUEST_TYPE_MISMATCH")

    if _has_contact_info(payload.handover_note or ""):
        raise BusinessError(
            "备注中不得包含联系方式，请使用结构化交接字段",
            code="CONTACT_INFO_FORBIDDEN",
            status_code=422,
        )

    now = utcnow()
    existing = db.execute(
        select(ContactRequest).where(
            ContactRequest.applicant_id == user.id,
            ContactRequest.candidate_public_id == payload.candidate_public_id,
        )
    ).scalars().all()
    for row in existing:
        if row.status in {ContactStatus.pending.value, ContactStatus.confirmed.value}:
            return row, True
        if row.cooldown_until is not None and row.cooldown_until > now:
            retry_after = int((row.cooldown_until - now).total_seconds())
            raise RateLimitError(
                f"申请失败次数较多，请 {retry_after} 秒后再试"
            )

    rate_limit.check_and_increment(
        db, subject_type="user", subject_id=user.id, action="contact_submit"
    )

    lock_key = _lock_key(user.id, candidate_type, item.id)
    contact = ContactRequest(
        request_type=payload.request_type,
        batch_id=batch.batch_id,
        candidate_public_id=payload.candidate_public_id,
        candidate_id=record.id,
        applicant_id=user.id,
        target_owner_id=item.user_id,
        target_item_type=candidate_type,
        target_item_id=item.id,
        private_verification=(payload.private_verification or "").strip() or None,
        handover_location_code=payload.handover_location_code,
        handover_window_start=payload.handover_window_start,
        handover_window_end=payload.handover_window_end,
        handover_note=payload.handover_note,
        status=ContactStatus.pending.value,
        failure_count=0,
        active_lock_key=lock_key,
        sensitive_category=item.category in SENSITIVE_CATEGORIES,
        created_at=now,
    )
    db.add(contact)
    record.disclosure_level = DisclosureLevel.verified.value
    db.flush()

    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="contact_submitted",
        entity_type="contact_request",
        entity_id=contact.id,
        batch_id=batch.batch_id,
        candidate_id=payload.candidate_public_id,
        disclosure_level=DisclosureLevel.verified.value,
        details={"request_type": payload.request_type},
    )
    notification_service.notify(
        db,
        user_id=item.user_id,
        event_type="contact_received",
        ref_type="contact_request",
        ref_id=contact.id,
    )
    db.commit()
    db.refresh(contact)
    return contact, False


def _to_out(contact: ContactRequest) -> ContactRequestOut:
    return ContactRequestOut(
        id=contact.id,
        request_type=contact.request_type,
        target_item_type=contact.target_item_type,
        target_item_id=contact.target_item_id,
        status=contact.status,
        created_at=contact.created_at,
    )


def list_me(db: Session, *, user: User) -> ContactRequestListOut:
    rows = db.execute(
        select(ContactRequest)
        .where(ContactRequest.applicant_id == user.id)
        .order_by(ContactRequest.created_at.desc())
    ).scalars().all()
    items = [
        ContactRequestListItem(
            id=row.id,
            request_type=row.request_type,
            batch_id=row.batch_id,
            candidate_public_id=row.candidate_public_id,
            target_item_type=row.target_item_type,
            target_item_id=row.target_item_id,
            status=row.status,
            created_at=row.created_at,
            decided_at=row.decided_at,
        )
        for row in rows
    ]
    return ContactRequestListOut(items=items, total=len(items))


def _candidate_summary(db: Session, contact: ContactRequest):
    record = disclosure_service.find_by_public_id(db, contact.candidate_public_id)
    if record is None:
        return None
    try:
        _, item, item_type = disclosure_service.resolve_candidate(
            db, batch_id=contact.batch_id, public_id=contact.candidate_public_id
        )
    except NotFoundError:
        return None
    return disclosure_service.build_summary(db, record, item, item_type)


def list_received(db: Session, *, user: User) -> ReceivedContactListOut:
    rows = db.execute(
        select(ContactRequest)
        .where(ContactRequest.target_owner_id == user.id)
        .order_by(ContactRequest.created_at.desc())
    ).scalars().all()
    items: list[ReceivedContactItem] = []
    for row in rows:
        item = get_item(db, row.target_item_type, row.target_item_id)
        items.append(
            ReceivedContactItem(
                id=row.id,
                request_type=row.request_type,
                target_item_title=item.title,
                candidate_summary=_candidate_summary(db, row),
                private_verification=row.private_verification,
                handover_location_code=row.handover_location_code,
                handover_window_start=row.handover_window_start,
                handover_window_end=row.handover_window_end,
                handover_note=row.handover_note,
                status=row.status,
                sensitive_category=bool(row.sensitive_category),
                created_at=row.created_at,
            )
        )
    return ReceivedContactListOut(items=items, total=len(items))


def get_detail(db: Session, *, user: User, contact: ContactRequest) -> ContactRequestDetailOut:
    item = get_item(db, contact.target_item_type, contact.target_item_id)
    return ContactRequestDetailOut(
        id=contact.id,
        request_type=contact.request_type,
        batch_id=contact.batch_id,
        candidate_public_id=contact.candidate_public_id,
        target_item_type=contact.target_item_type,
        target_item_id=contact.target_item_id,
        target_item_title=item.title,
        status=contact.status,
        private_verification=contact.private_verification,
        handover_location_code=contact.handover_location_code,
        handover_window_start=contact.handover_window_start,
        handover_window_end=contact.handover_window_end,
        handover_note=contact.handover_note,
        decision_note=contact.decision_note,
        failure_count=contact.failure_count,
        cooldown_until=contact.cooldown_until,
        sensitive_category=bool(contact.sensitive_category),
        created_at=contact.created_at,
        decided_at=contact.decided_at,
        candidate_summary=_candidate_summary(db, contact),
    )


def _load_pending(db: Session, contact: ContactRequest, user: User) -> tuple[MatchBatch, MatchRecord]:
    if contact.target_owner_id != user.id:
        raise NotFoundError("申请不存在")
    if contact.status != ContactStatus.pending.value:
        raise ConflictError("该申请已被处理", code="REQUEST_ALREADY_HANDLED")
    batch = db.execute(
        select(MatchBatch).where(MatchBatch.batch_id == contact.batch_id)
    ).scalars().first()
    if batch is None:
        raise ConflictError("匹配批次不存在", code="CANDIDATE_INVALID")
    record = disclosure_service.find_by_public_id(db, contact.candidate_public_id)
    if record is None:
        raise ConflictError("候选不存在", code="CANDIDATE_INVALID")
    return batch, record


def confirm(
    db: Session, *, user: User, contact: ContactRequest, payload: ContactConfirmRequest
) -> ContactConfirmOut:
    batch, record = _load_pending(db, contact, user)
    target = get_item(db, contact.target_item_type, contact.target_item_id)
    if payload.sensitive_verified is False and contact.sensitive_category:
        raise BusinessError(
            "敏感物品需先完成线下核验", code="INVALID_VERIFICATION", status_code=422
        )
    if target.status != S.active.value:
        raise ConflictError("目标记录状态已变化", code="ITEM_STATE_CHANGED")

    updated = db.execute(
        update(ContactRequest)
        .where(ContactRequest.id == contact.id, ContactRequest.status == ContactStatus.pending.value)
        .values(
            status=ContactStatus.confirmed.value,
            decider_id=user.id,
            decided_at=utcnow(),
            handover_location_code=payload.handover_location_code,
            handover_window_start=payload.handover_window_start,
            handover_window_end=payload.handover_window_end,
            handover_note=payload.handover_note,
            active_lock_key=None,
        )
    )
    if not updated.rowcount:
        db.rollback()
        raise ConflictError("申请已被并发处理", code="CONCURRENT_CONFIRM")

    assert_transition(target.status, S.claimed.value)
    target.status = S.claimed.value
    target.claimed_at = utcnow()

    initiated = get_item(db, batch.initiated_item_type, batch.initiated_item_id)
    if initiated.status == S.active.value:
        assert_transition(initiated.status, S.resolved.value)
        initiated.status = S.resolved.value
        initiated.claimed_at = utcnow()

    others = db.execute(
        select(ContactRequest).where(
            ContactRequest.id != contact.id,
            ContactRequest.target_item_type == contact.target_item_type,
            ContactRequest.target_item_id == contact.target_item_id,
            ContactRequest.status == ContactStatus.pending.value,
        )
    ).scalars().all()
    for other in others:
        other.status = ContactStatus.rejected.value
        other.decision_note = "other_request_confirmed"
        other.decided_at = utcnow()
        other.active_lock_key = None

    invalidated = db.execute(
        update(MatchBatch)
        .where(
            MatchBatch.status.in_(
                [
                    BatchStatus.processing.value,
                    BatchStatus.completed.value,
                    BatchStatus.degraded_completed.value,
                    BatchStatus.no_candidates.value,
                ]
            ),
            or_(
                (
                    (MatchBatch.initiated_item_type == contact.target_item_type)
                    & (MatchBatch.initiated_item_id == contact.target_item_id)
                ),
                (
                    (MatchBatch.initiated_item_type == batch.initiated_item_type)
                    & (MatchBatch.initiated_item_id == batch.initiated_item_id)
                ),
            ),
        )
        .values(status=BatchStatus.invalidated.value)
    ).rowcount
    db.execute(
        update(MatchRecord)
        .where(MatchRecord.candidate_public_id == contact.candidate_public_id)
        .values(candidate_status=CandidateStatus.confirmed.value)
    )

    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="contact_confirmed",
        entity_type="contact_request",
        entity_id=contact.id,
        batch_id=contact.batch_id,
        candidate_id=contact.candidate_public_id,
        disclosure_level=DisclosureLevel.handover.value,
        before_status=ContactStatus.pending.value,
        after_status=ContactStatus.confirmed.value,
    )
    notification_service.notify(
        db,
        user_id=contact.applicant_id,
        event_type="contact_confirmed",
        ref_type="contact_request",
        ref_id=contact.id,
    )
    notified = 1
    for other in others:
        notification_service.notify(
            db,
            user_id=other.applicant_id,
            event_type="contact_rejected",
            ref_type="contact_request",
            ref_id=other.id,
        )
        notified += 1
    db.commit()
    db.refresh(contact)

    return ContactConfirmOut(
        id=contact.id,
        status=contact.status,
        target_item_status=target.status,
        initiated_item_status=initiated.status,
        invalidated_batches=int(invalidated or 0),
        notified_users=notified,
    )


def reject(
    db: Session, *, user: User, contact: ContactRequest, payload: ContactRejectRequest
) -> ContactRequestOut:
    _load_pending(db, contact, user)
    if _has_contact_info(payload.decision_note):
        raise BusinessError(
            "拒绝理由不得包含联系方式", code="CONTACT_INFO_FORBIDDEN", status_code=422
        )
    now = utcnow()
    failure_count = int(contact.failure_count or 0) + 1
    cooldown_until = None
    if failure_count >= settings.contact_fail_threshold:
        cooldown_until = now + timedelta(hours=settings.contact_cooldown_hours)

    updated = db.execute(
        update(ContactRequest)
        .where(ContactRequest.id == contact.id, ContactRequest.status == ContactStatus.pending.value)
        .values(
            status=ContactStatus.rejected.value,
            decider_id=user.id,
            decision_note=payload.decision_note,
            decided_at=now,
            failure_count=failure_count,
            cooldown_until=cooldown_until,
            active_lock_key=None,
        )
    )
    if not updated.rowcount:
        db.rollback()
        raise ConflictError("申请已被并发处理", code="CONCURRENT_CONFIRM")

    record = disclosure_service.find_by_public_id(db, contact.candidate_public_id)
    if record is not None:
        record.disclosure_level = DisclosureLevel.summary.value

    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="contact_rejected",
        entity_type="contact_request",
        entity_id=contact.id,
        batch_id=contact.batch_id,
        candidate_id=contact.candidate_public_id,
        before_status=ContactStatus.pending.value,
        after_status=ContactStatus.rejected.value,
        reason=payload.decision_note,
    )
    if cooldown_until is not None:
        audit.record_audit(
            db,
            actor_id=user.id,
            action="cooldown_triggered",
            entity_type="contact_request",
            entity_id=contact.id,
            reason=f"failure_count={failure_count}",
        )
    notification_service.notify(
        db,
        user_id=contact.applicant_id,
        event_type="contact_rejected",
        ref_type="contact_request",
        ref_id=contact.id,
    )
    if cooldown_until is not None:
        notification_service.notify(
            db,
            user_id=contact.applicant_id,
            event_type="contact_cooldown",
            ref_type="contact_request",
            ref_id=contact.id,
        )
    db.commit()
    db.refresh(contact)
    return _to_out(contact)