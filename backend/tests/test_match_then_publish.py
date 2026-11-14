"""先匹配后发布：草稿 / 预览 / 确认发布主链路回归。"""

from __future__ import annotations

import pytest

from app.ai.provider import MockProvider
from app.api.v1 import drafts as drafts_api
from app.core.timeutil import utcnow
from app.db.enums import (
    BatchStatus,
    DraftStatus,
    NotificationType,
    ReviewTicketStatus,
)
from app.db.models import (
    FoundItem,
    LostItem,
    MatchBatch,
    MatchPreviewCandidate,
    Notification,
    ReviewTicket,
)
from app.schemas.item import LostItemCreate
from app.services import draft_service
from tests.conftest import ITEM_PAYLOAD


@pytest.fixture()
def mock_ai(monkeypatch):
    monkeypatch.setattr(
        "app.services.preview_service.get_provider", lambda: MockProvider()
    )
    return MockProvider()


def _payload(**overrides) -> LostItemCreate:
    body = dict(ITEM_PAYLOAD)
    body.update(overrides)
    return LostItemCreate(**body)


def _found(db, user, **overrides) -> FoundItem:
    body = {
        "user_id": user.id,
        "title": ITEM_PAYLOAD["title"],
        "description": ITEM_PAYLOAD["description"],
        "category": ITEM_PAYLOAD["category"],
        "location_text": ITEM_PAYLOAD["location_text"],
        "found_at": utcnow(),
        "status": "active",
        "is_removed": False,
        "visibility_scope": "match_disclosure",
        "info_sufficient": True,
        "data_version": 1,
        "review_round": 1,
    }
    body.update(overrides)
    item = FoundItem(**body)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_draft_preview_does_not_touch_formal_chain(
    db_session, user, other_user, mock_ai, match_first_mode
):
    _found(db_session, other_user)
    draft, replay = draft_service.create_draft(
        db_session, user=user, payload=_payload(), header_key=None
    )
    db_session.commit()

    assert replay is False
    assert draft.draft_id.startswith("d_")
    assert draft.status == DraftStatus.previewed.value
    assert db_session.query(LostItem).count() == 0
    assert db_session.query(ReviewTicket).count() == 0
    assert db_session.query(Notification).count() == 0

    batch = db_session.query(MatchBatch).one()
    assert batch.batch_kind == "preview"
    assert batch.threshold == 50.0
    assert batch.threshold_source == "preview"
    assert batch.initiated_item_type == "draft"
    assert batch.candidate_count >= 1
    assert db_session.query(MatchPreviewCandidate).count() >= 1


def test_preview_payload_whitelist(
    db_session, user, other_user, mock_ai, match_first_mode
):
    _found(db_session, other_user)
    draft, _ = draft_service.create_draft(
        db_session, user=user, payload=_payload(), header_key=None
    )
    out = drafts_api._preview_out(db_session, draft)

    assert out.draft_id == draft.draft_id
    assert out.threshold == 50.0
    assert out.threshold_source == "preview"
    assert out.candidate_count >= 1
    candidate = out.candidates[0]
    payload = candidate.model_dump()
    forbidden = {
        "object_key",
        "phone",
        "email",
        "student_no",
        "nickname",
        "user_id",
    }
    assert not (set(payload) & forbidden)
    assert candidate.item_type == "found"


def test_abandon_invalidates_preview(
    db_session, user, other_user, mock_ai, match_first_mode
):
    _found(db_session, other_user)
    draft, _ = draft_service.create_draft(
        db_session, user=user, payload=_payload(), header_key=None
    )
    db_session.commit()

    draft_service.abandon_draft(db_session, user=user, draft_id=draft.draft_id)
    db_session.commit()

    assert draft.status == DraftStatus.abandoned.value
    batch = db_session.query(MatchBatch).one()
    assert batch.status == BatchStatus.invalidated.value
    assert db_session.query(LostItem).count() == 0


def test_publish_creates_active_record_and_first_formal_threshold(
    db_session, user, other_user, mock_ai, match_first_mode
):
    _found(db_session, other_user)
    draft, _ = draft_service.create_draft(
        db_session, user=user, payload=_payload(), header_key=None
    )
    db_session.commit()

    result = draft_service.publish_draft(
        db_session, user=user, draft_id=draft.draft_id
    )
    db_session.commit()

    assert result["status"] == "active"
    assert result["publish_flow"] == "match_first"
    assert result["review_ticket_no"]
    assert draft.status == DraftStatus.published.value
    assert draft.published_item_id == result["item_id"]
    assert db_session.query(LostItem).count() == 1

    formal = db_session.query(MatchBatch).filter(
        MatchBatch.initiated_item_type == "lost"
    ).one()
    assert formal.batch_kind == "formal"
    assert formal.threshold == 50.0
    assert formal.threshold_source == "first_formal"

    ticket = db_session.query(ReviewTicket).one()
    assert ticket.status == ReviewTicketStatus.approved.value
    notices = db_session.query(Notification).all()
    assert any(n.type == NotificationType.listing_auto_approved.value for n in notices)


def test_publish_in_manual_mode_stays_pending(
    db_session, user, other_user, mock_ai
):
    _found(db_session, other_user)
    draft, _ = draft_service.create_draft(
        db_session, user=user, payload=_payload(), header_key=None
    )
    db_session.commit()

    result = draft_service.publish_draft(
        db_session, user=user, draft_id=draft.draft_id
    )
    db_session.commit()

    assert result["status"] == "pending_listing"
    assert db_session.query(LostItem).count() == 1
    assert (
        db_session.query(MatchBatch)
        .filter(MatchBatch.initiated_item_type == "lost")
        .count()
        == 0
    )