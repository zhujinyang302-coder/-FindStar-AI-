from __future__ import annotations

from app.api.v1.public import public_stats
from app.db.enums import ItemLifecycleStatus
from app.db.models import FoundItem
from tests.conftest import service_approve, service_create_item


def test_public_stats_only_completed_total(db_session, user, admin):
    item, ticket = service_create_item(db_session, user, item_type="found")
    service_approve(db_session, admin, ticket)
    assert public_stats(db_session).completed_total == 0

    row = db_session.get(FoundItem, item.id)
    row.status = ItemLifecycleStatus.resolved.value
    db_session.commit()
    assert public_stats(db_session).completed_total == 1

    payload = public_stats(db_session).model_dump()
    assert set(payload) == {"completed_total", "generated_at", "disclaimer"}


def test_public_stats_has_no_breakdown(db_session):
    payload = public_stats(db_session).model_dump()
    assert not {"categories", "locations", "lost_total", "found_total"} & set(payload)