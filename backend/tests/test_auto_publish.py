"""自动通过与人工审核双模式回归用例（服务层）。"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.config import settings
from app.core.response import BusinessError, ConflictError, GoneError, RateLimitError
from app.core.timeutil import utcnow
from app.db.enums import (
    NotificationType,
    ReviewTicketStatus,
    ReviewType,
)
from app.db.models import (
    AuditLog,
    FoundItem,
    MatchBatch,
    Notification,
    ReviewTicket,
    SecurityEvent,
)
from app.schemas.item import FoundItemCreate, ItemUpdate
from app.services import item_service, rate_limit, review_service
from tests.conftest import ITEM_PAYLOAD


def _payload(**overrides) -> FoundItemCreate:
    body = dict(ITEM_PAYLOAD)
    body.update(overrides)
    return FoundItemCreate(**body)


def _create(db, user):
    return item_service.create_item(
        db, user=user, item_type="found", payload=_payload()
    )


def test_auto_create_publishes_immediately(db_session, user, auto_mode):
    item, ticket = _create(db_session, user)
    db_session.commit()

    assert item.status == "active"
    assert item.visibility_scope == "match_disclosure"
    assert ticket.status == ReviewTicketStatus.approved.value
    assert ticket.source == "auto_approval"
    assert ticket.opinion == "系统自动通过"
    assert ticket.decided_at is not None

    pending = (
        db_session.query(ReviewTicket)
        .filter(
            ReviewTicket.review_type == ReviewType.listing.value,
            ReviewTicket.status == ReviewTicketStatus.pending.value,
        )
        .count()
    )
    assert pending == 0

    actions = [row.action for row in db_session.query(AuditLog).all()]
    assert "item_submit" in actions
    assert "item_auto_approved" in actions

    system_logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "item_auto_approved")
        .all()
    )
    assert len(system_logs) == 1
    assert system_logs[0].actor_id is None
    assert system_logs[0].actor_role == "system"

    notices = db_session.query(Notification).all()
    assert len(notices) == 1
    assert notices[0].type == NotificationType.listing_auto_approved.value
    assert all(n.type != NotificationType.review_result.value for n in notices)

    batch = db_session.query(MatchBatch).one()
    assert batch.status == "processing"
    assert batch.initiated_item_type == "found"


def test_manual_create_stays_pending(db_session, user):
    item, ticket = _create(db_session, user)
    db_session.commit()

    assert item.status == "pending_listing"
    assert item.visibility_scope == "owner_only"
    assert ticket.status == ReviewTicketStatus.pending.value
    assert ticket.source == "owner_request"

    notices = db_session.query(Notification).all()
    assert len(notices) == 1
    assert notices[0].type == NotificationType.review_result.value
    assert db_session.query(MatchBatch).count() == 0


def test_hard_risk_blocks_without_writes(db_session, user, monkeypatch):
    monkeypatch.setattr(settings, "listing_risk_denylist", ["违禁品"])
    payload = _payload(description="描述中包含违禁品信息，长度足够进行匹配校验")

    with pytest.raises(BusinessError) as exc:
        item_service.create_item(
            db_session, user=user, item_type="found", payload=payload
        )

    assert exc.value.code == "CONTENT_RISK_BLOCKED"
    assert exc.value.status_code == 422
    assert db_session.query(FoundItem).count() == 0
    events = db_session.query(SecurityEvent).all()
    assert any(row.event_type == "listing_risk_blocked" for row in events)


def test_soft_risk_publishes_with_sampling(db_session, user, auto_mode, monkeypatch):
    monkeypatch.setattr(settings, "listing_risk_soft_keywords", ["代购"])
    payload = _payload(description="描述中包含代购字样，长度足够进行匹配校验")

    item, _ = item_service.create_item(
        db_session, user=user, item_type="found", payload=payload
    )
    db_session.commit()

    assert item.status == "active"
    submit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "item_submit")
        .one()
    )
    assert submit.details["sampled"] is True
    assert any(
        row.event_type == "listing_risk_soft"
        for row in db_session.query(SecurityEvent).all()
    )


def test_listing_decide_retired_in_auto_mode(db_session, user, admin, monkeypatch):
    item, ticket = _create(db_session, user)
    monkeypatch.setattr(settings, "auto_approve_listing", True)

    with pytest.raises(GoneError) as exc:
        review_service.decide(
            db_session,
            admin=admin,
            ticket_no=ticket.ticket_no,
            decision="approve",
            opinion="同意",
        )

    assert exc.value.status_code == 410
    assert exc.value.code == "LISTING_REVIEW_RETIRED"


def test_manual_decide_still_works(db_session, user, admin):
    item, ticket = _create(db_session, user)
    out = review_service.decide(
        db_session,
        admin=admin,
        ticket_no=ticket.ticket_no,
        decision="approve",
        opinion="同意",
    )

    assert out.item_status == "active"
    assert out.match_task_created is True


def test_auto_update_reapproves_and_refreshes_batch(db_session, user, auto_mode):
    item, _ = _create(db_session, user)
    db_session.commit()
    old_batch = db_session.query(MatchBatch).one()

    updated, ticket = item_service.update_item(
        db_session,
        user=user,
        item_type="found",
        item_id=item.id,
        payload=ItemUpdate(title="新的标题"),
    )
    db_session.commit()

    assert updated.status == "active"
    assert updated.data_version == 2
    assert ticket.status == ReviewTicketStatus.approved.value
    assert ticket.source == "auto_approval"
    db_session.refresh(old_batch)
    assert old_batch.status == "invalidated"
    batches = (
        db_session.query(MatchBatch)
        .order_by(MatchBatch.id.desc())
        .all()
    )
    assert batches[0].status == "processing"


def test_auto_update_insufficient_info_rejected(db_session, user, auto_mode):
    item, _ = _create(db_session, user)
    db_session.commit()
    original_title = item.title

    with pytest.raises(BusinessError) as exc:
        item_service.update_item(
            db_session,
            user=user,
            item_type="found",
            item_id=item.id,
            payload=ItemUpdate(description="太短"),
        )
    assert exc.value.code == "INSUFFICIENT_INFO"
    db_session.rollback()
    db_session.refresh(item)
    assert item.title == original_title
    assert item.status == "active"


def test_auto_resubmit_reapproves(db_session, user, auto_mode):
    item, _ = _create(db_session, user)
    item.status = "listing_rejected"
    db_session.commit()

    result = item_service.resubmit(
        db_session, user=user, item_type="found", item_id=item.id
    )
    db_session.commit()

    assert result["status"] == "active"
    assert result["review_ticket_no"]


def test_auto_withdraw_conflict(db_session, user, auto_mode):
    item, _ = _create(db_session, user)

    with pytest.raises(ConflictError) as exc:
        item_service.withdraw(
            db_session, user=user, item_type="found", item_id=item.id
        )
    assert exc.value.code == "ITEM_NOT_WITHDRAWABLE"


def test_item_create_rate_limit(db_session, user, monkeypatch):
    monkeypatch.setattr(settings, "item_create_daily_limit", 3)
    for _ in range(3):
        rate_limit.check_and_increment(
            db_session,
            subject_type="user",
            subject_id=user.id,
            action="item_create",
        )
    with pytest.raises(RateLimitError):
        rate_limit.check_and_increment(
            db_session,
            subject_type="user",
            subject_id=user.id,
            action="item_create",
        )