from __future__ import annotations

import pytest

from app.core.response import ConflictError
from app.db.models import ContactRequest, MatchBatch, MatchRecord
from app.schemas.contact import ContactConfirmRequest, ContactCreateRequest
from app.services import contact_service, match_orchestrator
from tests.conftest import service_approve, service_create_item

LOST_PAYLOAD = {
    "title": "黑色双肩包",
    "description": "图书馆三楼自习区丢失黑色双肩包，包内有蓝色水杯和一本线性代数教材",
    "category": "钱包箱包",
    "color": "黑色",
    "location_code": "LIB-3F",
    "location_text": "图书馆三楼自习区",
}


def _prepare(db_session, user, other_user, admin):
    found, found_ticket = service_create_item(db_session, other_user, item_type="found")
    service_approve(db_session, admin, found_ticket)
    lost, lost_ticket = service_create_item(
        db_session, user, payload=LOST_PAYLOAD, item_type="lost"
    )
    service_approve(db_session, admin, lost_ticket)
    match_orchestrator.process_processing_batches(db_session)
    return found, lost


def test_repeated_accept_creates_single_batch(db_session, user, other_user, admin):
    found, ticket = service_create_item(db_session, other_user, item_type="found")
    service_approve(db_session, admin, ticket)

    first, _ = match_orchestrator.accept_match(
        db_session, user=other_user, lost_item_id=None, found_item_id=found.id
    )
    second, reused_again = match_orchestrator.accept_match(
        db_session, user=other_user, lost_item_id=None, found_item_id=found.id
    )
    assert reused_again is True
    assert first.id == second.id
    assert (
        db_session.query(MatchBatch)
        .filter(MatchBatch.initiated_item_type == "found")
        .count()
        == 1
    )


def test_concurrent_confirm_only_once(db_session, user, other_user, admin):
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
    first = contact_service.confirm(
        db_session,
        user=other_user,
        contact=contact,
        payload=ContactConfirmRequest(
            handover_location_code="LIB-1F",
            handover_window_start="2026-11-05T10:00:00",
            handover_window_end="2026-11-05T12:00:00",
            sensitive_verified=True,
        ),
    )
    assert first.status == "confirmed"
    db_session.expire_all()
    with pytest.raises(ConflictError):
        contact_service.confirm(
            db_session,
            user=other_user,
            contact=contact,
            payload=ContactConfirmRequest(
                handover_location_code="LIB-1F",
                handover_window_start="2026-11-05T10:00:00",
                handover_window_end="2026-11-05T12:00:00",
                sensitive_verified=True,
            ),
        )


def test_frequency_limit_blocks_matching(db_session, user, other_user, admin):
    from app.core.config import settings

    found, ticket = service_create_item(db_session, other_user, item_type="found")
    service_approve(db_session, admin, ticket)
    original = settings.match_item_daily_limit
    settings.match_item_daily_limit = 1
    try:
        match_orchestrator.accept_match(
            db_session, user=other_user, lost_item_id=None, found_item_id=found.id
        )
        # 数据版本未变时幂等复用；构造新数据版本以触发第二次计数
        found.data_version += 1
        db_session.commit()
        match_orchestrator.accept_match(
            db_session, user=other_user, lost_item_id=None, found_item_id=found.id
        )
        found.data_version += 1
        db_session.commit()
        with pytest.raises(Exception):
            match_orchestrator.accept_match(
                db_session, user=other_user, lost_item_id=None, found_item_id=found.id
            )
    finally:
        settings.match_item_daily_limit = original