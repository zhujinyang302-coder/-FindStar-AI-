from __future__ import annotations

import pytest

from app.core.response import ConflictError
from app.db.enums import ItemLifecycleStatus as S
from app.services.state_machine import (
    LEGAL_TRANSITIONS,
    assert_transition,
    can_transition,
    matchable_statuses,
)

_LEGAL = [
    (S.pending_listing.value, S.active.value),
    (S.pending_listing.value, S.listing_rejected.value),
    (S.pending_listing.value, S.closed.value),
    (S.active.value, S.delisting_review.value),
    (S.active.value, S.claimed.value),
    (S.active.value, S.resolved.value),
    (S.active.value, S.closed.value),
    (S.delisting_review.value, S.delisted.value),
    (S.delisting_review.value, S.active.value),
    (S.listing_rejected.value, S.pending_listing.value),
    (S.listing_rejected.value, S.closed.value),
    (S.delisted.value, S.pending_listing.value),
    (S.claimed.value, S.resolved.value),
    (S.resolved.value, S.closed.value),
]

_ILLEGAL = [
    (S.pending_listing.value, S.claimed.value),
    (S.active.value, S.pending_listing.value),
    (S.closed.value, S.active.value),
    (S.resolved.value, S.claimed.value),
    (S.delisted.value, S.active.value),
]


@pytest.mark.parametrize("current,target", _LEGAL)
def test_legal_edges(current, target):
    assert can_transition(current, target) is True
    assert_transition(current, target)


@pytest.mark.parametrize("current,target", _ILLEGAL)
def test_illegal_edges(current, target):
    assert can_transition(current, target) is False
    with pytest.raises(ConflictError):
        assert_transition(current, target)


def test_all_statuses_declared():
    assert set(LEGAL_TRANSITIONS) == {item.value for item in S}


def test_matchable_only_active():
    assert matchable_statuses() == frozenset({S.active.value})