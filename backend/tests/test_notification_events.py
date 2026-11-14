from __future__ import annotations

from app.db.enums import NotificationType
from app.db.models import MatchBatch, MatchRecord, Notification
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


def _notifications(db, user_id):
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.asc())
        .all()
    )


def test_review_result_notifications(db_session, user, admin):
    _, ticket = service_create_item(db_session, user, item_type="found")
    assert [x.type for x in _notifications(db_session, user.id)] == [
        NotificationType.review_result.value
    ]
    service_approve(db_session, admin, ticket)
    assert [x.type for x in _notifications(db_session, user.id)] == [
        NotificationType.review_result.value,
        NotificationType.review_result.value,
    ]


def test_contact_and_match_notifications(db_session, user, other_user, admin):
    found, found_ticket = service_create_item(db_session, other_user, item_type="found")
    service_approve(db_session, admin, found_ticket)
    lost, lost_ticket = service_create_item(
        db_session, user, payload=LOST_PAYLOAD, item_type="lost"
    )
    service_approve(db_session, admin, lost_ticket)
    match_orchestrator.process_processing_batches(db_session)

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
    assert NotificationType.contact_received.value in [
        x.type for x in _notifications(db_session, other_user.id)
    ]

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
    assert NotificationType.contact_confirmed.value in [
        x.type for x in _notifications(db_session, user.id)
    ]