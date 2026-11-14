from __future__ import annotations

import pytest

from app.core.response import RateLimitError
from app.services import rate_limit


def test_counter_increments_until_limit(db_session):
    for _ in range(3):
        rate_limit.check_and_increment(
            db_session, subject_type="user", subject_id=1, action="match_request", limit=3
        )
    assert rate_limit.current_count(
        db_session, subject_type="user", subject_id=1, action="match_request"
    ) == 3
    with pytest.raises(RateLimitError):
        rate_limit.check_and_increment(
            db_session, subject_type="user", subject_id=1, action="match_request", limit=3
        )


def test_subjects_are_isolated(db_session):
    rate_limit.check_and_increment(
        db_session, subject_type="user", subject_id=1, action="match_request", limit=1
    )
    rate_limit.check_and_increment(
        db_session, subject_type="user", subject_id=2, action="match_request", limit=1
    )
    assert rate_limit.current_count(
        db_session, subject_type="user", subject_id=1, action="match_request"
    ) == 1
    assert rate_limit.current_count(
        db_session, subject_type="user", subject_id=2, action="match_request"
    ) == 1


def test_default_limits_follow_settings():
    from app.core.config import settings

    assert rate_limit.limit_for("match_request") == settings.match_user_daily_limit
    assert rate_limit.limit_for("contact_submit") == settings.contact_daily_limit