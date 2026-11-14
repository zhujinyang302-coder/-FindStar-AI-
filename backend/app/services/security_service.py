"""反滥用异常检测与安全事件。"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger, request_id_var
from app.core.timeutil import utcnow
from app.db.models import DisclosureAccessLog, SecurityEvent

logger = get_logger(__name__)


def record_event(
    db: Session,
    *,
    actor_id: int | None,
    event_type: str,
    severity: str = "warning",
    detail: dict | None = None,
) -> SecurityEvent:
    event = SecurityEvent(
        actor_id=actor_id,
        event_type=event_type,
        severity=severity,
        detail=detail,
        request_id=request_id_var.get(),
        created_at=utcnow(),
    )
    db.add(event)
    logger.warning("security event", extra={"error_category": event_type})
    return event


def check_view_burst(db: Session, *, actor_id: int) -> bool:
    """5 分钟内查看不同候选 ≥ security_view_burst 次则记录事件。"""
    since = utcnow() - timedelta(minutes=5)
    distinct = db.execute(
        select(func.count(func.distinct(DisclosureAccessLog.candidate_public_id)))
        .where(
            DisclosureAccessLog.actor_id == actor_id,
            DisclosureAccessLog.created_at >= since,
        )
    ).scalar_one()
    if int(distinct) >= settings.security_view_burst:
        exists = db.execute(
            select(SecurityEvent.id).where(
                SecurityEvent.actor_id == actor_id,
                SecurityEvent.event_type == "view_burst",
                SecurityEvent.created_at >= since,
            )
        ).scalar_one_or_none()
        if exists is None:
            record_event(
                db,
                actor_id=actor_id,
                event_type="view_burst",
                detail={"distinct_candidates": int(distinct)},
            )
        return True
    return False