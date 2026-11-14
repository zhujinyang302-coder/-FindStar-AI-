from __future__ import annotations

import pytest

from app.core.response import NotFoundError
from app.services import disclosure_service
from app.services.visibility_policy import matrix_snapshot

_FORBIDDEN_KEYS = {
    "owner_id",
    "owner_nickname",
    "phone",
    "email",
    "full_description",
    "original_url",
    "private_verification",
    "private_evidence",
}


def test_visibility_matrix_snapshot_is_complete():
    snapshot = matrix_snapshot()
    assert len(snapshot) == 8
    assert all(row["other_detail"] is False for row in snapshot.values())


def test_candidate_public_id_is_not_guessable():
    public_id = disclosure_service.candidate_public_id("b_batch", "found", 42)
    assert public_id.startswith("c_")
    assert len(public_id) == 34
    assert public_id != disclosure_service.candidate_public_id("b_batch", "found", 43)
    # 不同批次即便候选相同也不应得到相同标识
    assert public_id != disclosure_service.candidate_public_id("b_other", "found", 42)


def test_unknown_public_id_not_found(db_session):
    with pytest.raises(NotFoundError):
        disclosure_service.resolve_candidate(
            db_session, batch_id="b_missing", public_id="c_forged"
        )