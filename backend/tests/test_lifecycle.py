from __future__ import annotations

from datetime import timedelta

from app.core.config import settings
from app.core.timeutil import utcnow
from app.db.enums import BatchStatus
from app.db.models import MatchBatch
from app.services import lifecycle


def _batch(db, *, status: str, expired: bool = False, age_days: int = 0) -> MatchBatch:
    batch = MatchBatch(
        batch_id=f"b_{utcnow().timestamp()}_{status}",
        idempotency_key=f"key_{utcnow().timestamp()}_{status}_{age_days}",
        initiated_item_type="lost",
        initiated_item_id=1,
        initiator_id=1,
        direction="lost_to_found",
        status=status,
        algorithm_version="v3",
        config_version="v3",
        data_version=1,
        threshold=65.0,
        quota=3,
        created_at=utcnow() - timedelta(days=age_days),
        expires_at=(utcnow() - timedelta(seconds=1)) if expired else (utcnow() + timedelta(days=1)),
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def test_expire_completed_batches(db_session):
    expired = _batch(
        db_session, status=BatchStatus.completed.value, expired=True
    )
    alive = _batch(db_session, status=BatchStatus.completed.value, expired=False)
    assert lifecycle.expire(db_session) == 1
    db_session.commit()
    db_session.refresh(expired)
    db_session.refresh(alive)
    assert expired.status == BatchStatus.expired.value
    assert alive.status == BatchStatus.completed.value


def test_archive_after_retention(db_session):
    old = _batch(
        db_session,
        status=BatchStatus.expired.value,
        age_days=settings.match_batch_retention_days + 1,
    )
    recent = _batch(db_session, status=BatchStatus.expired.value, age_days=1)
    assert lifecycle.archive(db_session) == 1
    db_session.commit()
    db_session.refresh(old)
    db_session.refresh(recent)
    assert old.status == BatchStatus.archived.value
    assert recent.status == BatchStatus.expired.value


def test_cleanup_removes_old_rows(db_session):
    result = lifecycle.cleanup(db_session)
    assert set(result) == {"notifications", "disclosure_logs", "rate_counters"}