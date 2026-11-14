from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.v1 import legacy
from app.core.config import Settings
from app.core.response import GoneError, NotFoundError
from tests.conftest import service_create_item


def _assert_gone(func, *args):
    with pytest.raises(GoneError) as info:
        func(*args)
    assert info.value.code == "FLOW_CHANGED"
    assert info.value.status_code == 410


def test_old_list_endpoints_return_410():
    _assert_gone(legacy.legacy_list_items)
    _assert_gone(legacy.legacy_search)
    _assert_gone(legacy.legacy_stats)


def test_old_claim_and_admin_endpoints_return_410():
    _assert_gone(legacy.legacy_create_claim)
    _assert_gone(legacy.legacy_my_claims)
    _assert_gone(legacy.legacy_admin_claims)
    _assert_gone(legacy.legacy_admin_claim_detail, 1)
    _assert_gone(legacy.legacy_admin_claim_review, 1)
    _assert_gone(legacy.legacy_admin_statistics)
    _assert_gone(legacy.legacy_admin_remove_item, "found", 1)
    _assert_gone(legacy.legacy_update_item, "found", 1)
    _assert_gone(legacy.legacy_match_detail, 1)


def test_legacy_detail_owner_only(db_session, user, other_user, admin):
    item, _ = service_create_item(db_session, other_user, item_type="found")
    owner_result = legacy.legacy_item_detail(
        item.id, None, db_session, other_user
    )
    assert owner_result.id == item.id
    with pytest.raises(NotFoundError):
        legacy.legacy_item_detail(item.id, None, db_session, user)
    with pytest.raises(NotFoundError):
        legacy.legacy_item_detail(item.id, None, db_session, admin)
    with pytest.raises(NotFoundError):
        legacy.legacy_item_detail(item.id, None, db_session, None)


def test_gone_error_has_new_path_hint():
    error = GoneError("请使用 /api/v1/public/stats")
    assert error.status_code == 410
    assert error.code == "FLOW_CHANGED"


def test_config_rejects_out_of_range_quota():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, match_candidate_quota=8)


def test_config_rejects_out_of_range_threshold():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, match_score_threshold=120)


def test_config_rejects_degraded_budget_gt_total():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            match_total_budget_seconds=3.0,
            match_degraded_budget_seconds=5.0,
        )


def test_config_defaults():
    configured = Settings(_env_file=None)
    assert configured.match_score_threshold == 65.0
    assert configured.match_candidate_quota == 3
    assert configured.contact_fail_threshold == 3
    assert configured.contact_cooldown_hours == 24