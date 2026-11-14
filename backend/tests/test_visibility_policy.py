from __future__ import annotations

import pytest

from app.db.enums import ItemLifecycleStatus as S
from app.services.visibility_policy import (
    can_initiate_match,
    can_join_candidate_pool,
    can_process_request,
    can_review,
    can_view_other_detail,
    can_view_own_detail,
    matrix_snapshot,
    public_statistics_scope,
)

_STATUSES = [item.value for item in S]


def test_own_detail_always_visible():
    for status in _STATUSES:
        assert can_view_own_detail(status) is True


def test_other_detail_never_visible():
    for status in _STATUSES:
        assert can_view_other_detail(status) is False


@pytest.mark.parametrize(
    "status,pool,initiate,process",
    [
        (S.pending_listing.value, False, False, False),
        (S.active.value, True, True, True),
        (S.listing_rejected.value, False, False, False),
        (S.delisting_review.value, False, False, True),
        (S.delisted.value, False, False, False),
        (S.claimed.value, False, False, True),
        (S.resolved.value, False, False, False),
        (S.closed.value, False, False, False),
    ],
)
def test_matrix_cells(status, pool, initiate, process):
    assert can_join_candidate_pool(status) is pool
    assert can_initiate_match(status) is initiate
    assert can_process_request(status) is process
    assert can_review(status) is True


def test_matrix_snapshot_shape():
    snapshot = matrix_snapshot()
    assert set(snapshot) == set(_STATUSES)
    for row in snapshot.values():
        assert set(row) == {
            "own_detail",
            "other_detail",
            "candidate_pool",
            "initiate_match",
            "process_request",
            "review",
        }


def test_public_scope_only_completed_total():
    assert public_statistics_scope() == frozenset({"completed_total"})