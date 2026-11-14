from __future__ import annotations

import pytest

from app.core.response import ValidationError
from app.schemas.admin import MatchConfigCreateRequest, WeightsOut
from app.services import quality_service


def test_metrics_shape(db_session):
    result = quality_service.metrics(db_session)
    payload = result.model_dump()
    assert set(payload) == {
        "match_requests",
        "no_candidate_rate",
        "top3_hit_rate",
        "user_false_positive_rate",
        "degraded_rate",
        "candidate_p95_ms",
        "period_label",
        "generated_at",
        "note",
    }
    assert payload["note"] == "聚合口径，不含任何候选内容与用户身份"


def test_config_version_requires_reason(db_session, admin):
    with pytest.raises(Exception):
        MatchConfigCreateRequest(
            threshold=65, quota=3, time_window_days=30, reason="短"
        )


def test_weights_must_sum_to_one():
    with pytest.raises(Exception):
        MatchConfigCreateRequest(
            threshold=65,
            quota=3,
            time_window_days=30,
            weights=WeightsOut(
                text=0.5, image=0.5, location=0.5, time=0.5, attribute=0.5
            ),
            reason="调整权重配置",
        )


def test_create_config_replaces_active(db_session, admin):
    payload = MatchConfigCreateRequest(
        threshold=70.0,
        quota=2,
        time_window_days=21,
        reason="提升精度降低误报",
    )
    created = quality_service.create_config_version(db_session, admin=admin, payload=payload)
    assert created.active is True
    versions = quality_service.list_config_versions(db_session)
    assert versions.items[0].threshold == 70.0
    assert versions.items[0].active is True


def test_quota_upper_bound(db_session, admin):
    payload = MatchConfigCreateRequest(
        threshold=70.0, quota=5, time_window_days=21, reason="提升召回数量"
    )
    created = quality_service.create_config_version(db_session, admin=admin, payload=payload)
    assert created.quota == 5