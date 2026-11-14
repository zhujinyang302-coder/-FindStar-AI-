from __future__ import annotations

from datetime import timedelta

from app.core.timeutil import utcnow
from app.db.enums import ItemLifecycleStatus
from app.db.models import FoundItem, LostItem
from app.services.recall_service import build_candidate_pool

NOW = utcnow()


def _lost(db, user, **overrides) -> LostItem:
    data = dict(
        user_id=user.id,
        title="黑色双肩包",
        description="图书馆丢失黑色双肩包，包内有蓝色水杯和教材" * 2,
        category="钱包箱包",
        color="黑色",
        location_code="LIB-3F",
        location_text="图书馆三楼",
        lost_at=NOW - timedelta(days=2),
        status=ItemLifecycleStatus.active.value,
        is_removed=False,
        info_sufficient=True,
        data_version=1,
    )
    data.update(overrides)
    item = LostItem(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _found(db, user, **overrides) -> FoundItem:
    data = dict(
        user_id=user.id,
        title="黑色双肩包",
        description="图书馆三楼拾到黑色双肩包，包内有蓝色水杯" * 2,
        category="钱包箱包",
        color="黑色",
        location_code="LIB-3F",
        location_text="图书馆三楼",
        found_at=NOW - timedelta(days=1),
        status=ItemLifecycleStatus.active.value,
        is_removed=False,
        info_sufficient=True,
        data_version=1,
    )
    data.update(overrides)
    item = FoundItem(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _pool(db, lost, window_days=30, pool_max=2000):
    return build_candidate_pool(
        db,
        initiated_item=lost,
        initiated_type="lost",
        initiator_id=lost.user_id,
        window_days=window_days,
        pool_max=pool_max,
    )


def test_matching_candidate_kept(db_session, user, other_user):
    lost = _lost(db_session, user)
    found = _found(db_session, other_user)
    result = _pool(db_session, lost)
    assert [item.id for _, item in result.candidates] == [found.id]
    assert result.filter_stats["same_user"] == 0


def test_same_user_excluded(db_session, user):
    lost = _lost(db_session, user)
    _found(db_session, user)
    result = _pool(db_session, lost)
    assert result.candidates == []
    assert result.filter_stats["same_user"] == 1


def test_category_conflict_excluded(db_session, user, other_user):
    lost = _lost(db_session, user)
    _found(db_session, other_user, category="电子产品")
    result = _pool(db_session, lost)
    assert result.candidates == []
    assert result.filter_stats["category_conflict"] == 1


def test_time_window_excluded(db_session, user, other_user):
    lost = _lost(db_session, user)
    _found(db_session, other_user, found_at=NOW - timedelta(days=40))
    result = _pool(db_session, lost, window_days=30)
    assert result.candidates == []
    assert result.filter_stats["time_window"] == 1


def test_time_direction_excluded(db_session, user, other_user):
    lost = _lost(db_session, user, lost_at=NOW - timedelta(days=1))
    _found(db_session, other_user, found_at=NOW - timedelta(days=10))
    result = _pool(db_session, lost)
    assert result.candidates == []
    assert result.filter_stats["time_direction"] == 1


def test_invalid_status_excluded(db_session, user, other_user):
    lost = _lost(db_session, user)
    _found(db_session, other_user, status=ItemLifecycleStatus.claimed.value)
    result = _pool(db_session, lost)
    assert result.candidates == []


def test_truncation_marks_flag(db_session, user, other_user):
    lost = _lost(db_session, user)
    for index in range(4):
        _found(db_session, other_user, title=f"黑色双肩包{index}")
    result = _pool(db_session, lost, pool_max=2)
    assert len(result.candidates) == 2
    assert result.truncated is True