from __future__ import annotations

import pytest

from app.api import deps
from app.core.response import ConflictError, ForbiddenError, NotFoundError
from app.db.enums import ItemLifecycleStatus
from app.db.models import ContactRequest, FoundItem, LostItem, MatchBatch, MatchRecord
from app.schemas.contact import (
    ContactConfirmRequest,
    ContactCreateRequest,
    ContactRejectRequest,
)
from app.services import contact_service, disclosure_service, match_orchestrator
from tests.conftest import service_approve, service_create_item

LOST_PAYLOAD = {
    "title": "黑色双肩包",
    "description": "图书馆三楼自习区丢失黑色双肩包，包内有蓝色水杯和一本线性代数教材",
    "category": "钱包箱包",
    "color": "黑色",
    "location_code": "LIB-3F",
    "location_text": "图书馆三楼自习区",
}

_FORBIDDEN = {
    "owner_id",
    "owner_nickname",
    "phone",
    "email",
    "full_description",
    "original_url",
    "private_verification",
    "user_id",
}


def _prepare(db_session, user, other_user, admin):
    found, found_ticket = service_create_item(db_session, other_user, item_type="found")
    assert found.status == ItemLifecycleStatus.pending_listing.value
    service_approve(db_session, admin, found_ticket)
    lost, lost_ticket = service_create_item(
        db_session, user, payload=LOST_PAYLOAD, item_type="lost"
    )
    service_approve(db_session, admin, lost_ticket)
    match_orchestrator.process_processing_batches(db_session)
    return found, lost


def test_pending_item_cannot_match(db_session, user, other_user):
    found, _ = service_create_item(db_session, other_user, item_type="found")
    with pytest.raises(ConflictError):
        match_orchestrator.accept_match(
            db_session, user=other_user, lost_item_id=None, found_item_id=found.id
        )


def test_full_bidirectional_flow(db_session, user, other_user, admin):
    found, lost = _prepare(db_session, user, other_user, admin)

    batches = db_session.query(MatchBatch).all()
    assert len(batches) == 2
    lost_batch = next(
        batch for batch in batches if batch.initiated_item_type == "lost"
    )
    assert lost_batch.status in {"completed", "degraded_completed"}
    assert lost_batch.candidate_count >= 1

    records = (
        db_session.query(MatchRecord)
        .filter(MatchRecord.batch_id == lost_batch.batch_id)
        .all()
    )
    assert records
    record = records[0]
    candidate_item = db_session.get(FoundItem, record.candidate_item_id)
    summary = disclosure_service.build_summary(
        db_session, record, candidate_item, "found"
    )
    payload = summary.model_dump()
    assert not _FORBIDDEN & set(payload)
    assert payload["candidate_public_id"].startswith("c_")
    assert "title_excerpt" in payload and "description_excerpt" in payload

    contact, reused = contact_service.submit(
        db_session,
        user=user,
        payload=ContactCreateRequest(
            batch_id=lost_batch.batch_id,
            candidate_public_id=record.candidate_public_id,
            request_type="claim",
            private_verification="包内水杯底部有姓名缩写，教材扉页有班级",
            handover_location_code="LIB-1F-SERVICE",
        ),
    )
    assert reused is False
    assert contact.status == "pending"

    again, reused = contact_service.submit(
        db_session,
        user=user,
        payload=ContactCreateRequest(
            batch_id=lost_batch.batch_id,
            candidate_public_id=record.candidate_public_id,
            request_type="claim",
            private_verification="包内水杯底部有姓名缩写，教材扉页有班级",
        ),
    )
    assert reused is True
    assert again.id == contact.id

    received = contact_service.list_received(db_session, user=other_user)
    assert received.total == 1
    assert received.items[0].private_verification

    with pytest.raises(NotFoundError):
        deps.get_request_party(contact.id, db_session, admin)

    result = contact_service.confirm(
        db_session,
        user=other_user,
        contact=contact,
        payload=ContactConfirmRequest(
            handover_location_code="LIB-1F-SERVICE",
            handover_window_start="2026-11-05T10:00:00",
            handover_window_end="2026-11-05T12:00:00",
            sensitive_verified=True,
        ),
    )
    assert result.status == "confirmed"
    assert result.target_item_status == ItemLifecycleStatus.claimed.value
    assert result.initiated_item_status == ItemLifecycleStatus.resolved.value

    db_session.expire_all()
    assert db_session.get(FoundItem, found.id).status == ItemLifecycleStatus.claimed.value
    assert db_session.get(LostItem, lost.id).status == ItemLifecycleStatus.resolved.value

    detail = contact_service.get_detail(db_session, user=user, contact=contact)
    assert detail.handover_location_code == "LIB-1F-SERVICE"
    assert detail.status == "confirmed"


def test_direction_mismatch(db_session, user, other_user, admin):
    _prepare(db_session, user, other_user, admin)
    batch = (
        db_session.query(MatchBatch)
        .filter(MatchBatch.initiated_item_type == "lost")
        .first()
    )
    record = (
        db_session.query(MatchRecord)
        .filter(MatchRecord.batch_id == batch.batch_id)
        .first()
    )
    with pytest.raises(ConflictError) as info:
        contact_service.submit(
            db_session,
            user=user,
            payload=ContactCreateRequest(
                batch_id=batch.batch_id,
                candidate_public_id=record.candidate_public_id,
                request_type="return_clue",
                private_verification="这是一段符合长度要求的核验说明文字",
            ),
        )
    assert info.value.code == "REQUEST_TYPE_MISMATCH"


def test_admin_cannot_use_match_domain(db_session, admin):
    with pytest.raises(ForbiddenError) as info:
        deps.require_non_admin(admin, db_session)
    assert info.value.code == "ADMIN_NOT_ALLOWED"


def test_reject_releases_lock(db_session, user, other_user, admin):
    _prepare(db_session, user, other_user, admin)
    batch = (
        db_session.query(MatchBatch)
        .filter(MatchBatch.initiated_item_type == "lost")
        .first()
    )
    record = (
        db_session.query(MatchRecord)
        .filter(MatchRecord.batch_id == batch.batch_id)
        .first()
    )
    contact, _ = contact_service.submit(
        db_session,
        user=user,
        payload=ContactCreateRequest(
            batch_id=batch.batch_id,
            candidate_public_id=record.candidate_public_id,
            request_type="claim",
            private_verification="包内水杯底部有姓名缩写，教材扉页有班级",
        ),
    )
    rejected = contact_service.reject(
        db_session,
        user=other_user,
        contact=contact,
        payload=ContactRejectRequest(decision_note="核验信息不足，请补充更多特征"),
    )
    assert rejected.status == "rejected"
    db_session.expire_all()
    again = db_session.get(ContactRequest, contact.id)
    assert again.failure_count == 1
    assert again.active_lock_key is None