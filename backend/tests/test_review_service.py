from __future__ import annotations

import pytest

from app.core.response import ConflictError, ForbiddenError
from app.db.enums import ItemLifecycleStatus, ReviewTicketStatus
from app.schemas.admin import ReviewDecisionRequest
from app.services import review_service
from tests.conftest import service_create_item


def test_review_queue_contains_listing_ticket(db_session, user):
    item, ticket = service_create_item(db_session, user, item_type="found")
    queue = review_service.list_tickets(
        db_session, review_type="listing", source=None, overdue=None, page=1, page_size=20
    )
    assert queue.total == 1
    assert queue.items[0].ticket_no == ticket.ticket_no
    assert queue.items[0].item_title == item.title


def test_review_detail_isolated_from_match_data(db_session, user):
    _, ticket = service_create_item(db_session, user, item_type="found")
    detail = review_service.get_ticket(db_session, ticket.ticket_no)
    payload = detail.model_dump()
    assert not {"candidate", "score", "private_verification", "applicant_id"} & set(
        payload
    )
    assert payload["disclaimer"] == "匹配结果不参与审核结论"


def test_approve_listing_creates_match_task(db_session, user, admin):
    item, ticket = service_create_item(db_session, user, item_type="found")
    result = review_service.decide(
        db_session,
        admin=admin,
        ticket_no=ticket.ticket_no,
        decision="approve",
        opinion="资料齐全，同意上架",
    )
    db_session.refresh(item)
    assert item.status == ItemLifecycleStatus.active.value
    assert result.status == ReviewTicketStatus.approved.value
    assert result.match_task_created is True


def test_reject_listing_requires_opinion():
    with pytest.raises(Exception):
        ReviewDecisionRequest(decision="reject", opinion=None)
    with pytest.raises(Exception):
        ReviewDecisionRequest(decision="reject", opinion="短")


def test_reject_listing_sets_rejected_status(db_session, user, admin):
    item, ticket = service_create_item(db_session, user, item_type="found")
    review_service.decide(
        db_session,
        admin=admin,
        ticket_no=ticket.ticket_no,
        decision="reject",
        opinion="描述不足，请补充物品特征",
    )
    db_session.refresh(item)
    assert item.status == ItemLifecycleStatus.listing_rejected.value


def test_duplicate_decision_conflicts(db_session, user, admin):
    _, ticket = service_create_item(db_session, user, item_type="found")
    review_service.decide(
        db_session,
        admin=admin,
        ticket_no=ticket.ticket_no,
        decision="approve",
        opinion="资料齐全，同意上架",
    )
    with pytest.raises(ConflictError):
        review_service.decide(
            db_session,
            admin=admin,
            ticket_no=ticket.ticket_no,
            decision="approve",
            opinion="重复决定",
        )


def test_self_review_forbidden(db_session, admin):
    _, ticket = service_create_item(db_session, admin, item_type="found")
    with pytest.raises(ForbiddenError):
        review_service.decide(
            db_session,
            admin=admin,
            ticket_no=ticket.ticket_no,
            decision="approve",
            opinion="资料齐全，同意上架",
        )


def test_delist_requires_review(db_session, user, admin):
    item, listing_ticket = service_create_item(db_session, user, item_type="found")
    review_service.decide(
        db_session,
        admin=admin,
        ticket_no=listing_ticket.ticket_no,
        decision="approve",
        opinion="资料齐全，同意上架",
    )
    ticket = review_service.apply_delist(
        db_session, user=user, item_type="found", item_id=item.id, reason="物品已找回，申请下架"
    )
    db_session.refresh(item)
    assert item.status == ItemLifecycleStatus.delisting_review.value
    result = review_service.decide(
        db_session,
        admin=admin,
        ticket_no=ticket.ticket_no,
        decision="approve",
        opinion="核实无误，同意下架",
    )
    db_session.refresh(item)
    assert item.status == ItemLifecycleStatus.delisted.value
    assert result.status == ReviewTicketStatus.approved.value