"""匹配结果生命周期：过期、失效、归档与清理。"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.cache import get_cache
from app.core.config import settings
from app.core.timeutil import utcnow
from app.db.enums import BatchStatus
from app.db.models import (
    DisclosureAccessLog,
    MatchBatch,
    MatchRecord,
    Notification,
    RateLimitCounter,
)

_CACHE_PREFIXES = (
    "findstar:items:my:",
    "findstar:batch:",
    "findstar:cand:",
    "findstar:notify:",
    "findstar:quality:",
)


def invalidate_after_change(db: Session, *, item_type: str, item_id: int) -> int:
    """记录变更/下架/删除/认领后，相关批次 60 秒内不可见。"""
    batches = db.execute(
        select(MatchBatch).where(
            MatchBatch.status.in_(
                [
                    BatchStatus.processing.value,
                    BatchStatus.completed.value,
                    BatchStatus.degraded_completed.value,
                    BatchStatus.no_candidates.value,
                ]
            )
        )
    ).scalars().all()
    related = [
        batch
        for batch in batches
        if (batch.initiated_item_type == item_type and batch.initiated_item_id == item_id)
        or _batch_has_candidate(db, batch, item_type, item_id)
    ]
    for batch in related:
        batch.status = BatchStatus.invalidated.value
    if related:
        db.execute(
            update(MatchRecord)
            .where(MatchRecord.batch_id.in_([b.batch_id for b in related]))
            .values(candidate_status="invalidated")
        )
    _flush_cache()
    return len(related)


def _batch_has_candidate(db: Session, batch: MatchBatch, item_type: str, item_id: int) -> bool:
    row = db.execute(
        select(MatchRecord.id).where(
            MatchRecord.batch_id == batch.batch_id,
            MatchRecord.candidate_item_type == item_type,
            MatchRecord.candidate_item_id == item_id,
        )
    ).scalar_one_or_none()
    return row is not None


def _flush_cache() -> None:
    cache = get_cache()
    for prefix in _CACHE_PREFIXES:
        cache.delete_prefix(prefix)


def expire(db: Session) -> int:
    now = utcnow()
    rows = db.execute(
        select(MatchBatch).where(
            MatchBatch.status.in_(
                [
                    BatchStatus.completed.value,
                    BatchStatus.degraded_completed.value,
                    BatchStatus.no_candidates.value,
                ]
            ),
            MatchBatch.expires_at.is_not(None),
            MatchBatch.expires_at <= now,
        )
    ).scalars().all()
    for batch in rows:
        batch.status = BatchStatus.expired.value
    db.flush()
    return len(rows)


def archive(db: Session) -> int:
    cutoff = utcnow() - timedelta(days=settings.match_batch_retention_days)
    rows = db.execute(
        select(MatchBatch).where(
            MatchBatch.status.in_(
                [BatchStatus.invalidated.value, BatchStatus.expired.value]
            ),
            MatchBatch.created_at <= cutoff,
        )
    ).scalars().all()
    for batch in rows:
        batch.status = BatchStatus.archived.value
    db.flush()
    return len(rows)


def cleanup(db: Session) -> dict[str, int]:
    now = utcnow()
    notifications = db.execute(
        delete(Notification).where(Notification.created_at <= now - timedelta(days=90))
    ).rowcount
    disclosures = db.execute(
        delete(DisclosureAccessLog).where(
            DisclosureAccessLog.created_at <= now - timedelta(days=180)
        )
    ).rowcount
    counters = db.execute(
        delete(RateLimitCounter).where(
            RateLimitCounter.window_start
            <= (now - timedelta(days=30)).strftime("%Y-%m-%d")
        )
    ).rowcount
    return {
        "notifications": int(notifications or 0),
        "disclosure_logs": int(disclosures or 0),
        "rate_counters": int(counters or 0),
    }