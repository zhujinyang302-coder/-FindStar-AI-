from __future__ import annotations

from app.api.v1 import admin_review
from app.db.enums import ReviewTicketStatus
from tests.conftest import service_approve, service_create_item


def test_review_history_lists_decided_ticket(db_session, user, admin):
    _, ticket = service_create_item(db_session, user, item_type="found")
    service_approve(db_session, admin, ticket)

    history = admin_review.review_history(
        review_type="listing",
        source=None,
        page=1,
        page_size=20,
        db=db_session,
        admin=admin,
    )
    assert history.total == 1
    assert history.items[0].ticket_no == ticket.ticket_no
    assert history.items[0].status == ReviewTicketStatus.approved.value


def test_review_history_excludes_pending(db_session, user, admin):
    service_create_item(db_session, user, item_type="found")
    history = admin_review.review_history(
        review_type="listing",
        source=None,
        page=1,
        page_size=20,
        db=db_session,
        admin=admin,
    )
    assert history.total == 0