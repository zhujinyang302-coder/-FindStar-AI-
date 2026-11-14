"""后台调度：匹配执行补偿、失效扫描、通知重试、过期提醒与数据清理。

任务状态持久化在 match_batches，进程重启后可继续执行；
多实例部署时通过 BACKGROUND_JOBS_ENABLED=false 关闭进程内调度，改用外部 cron。
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.timeutil import utcnow
from app.db.enums import BatchStatus
from app.db.models import MatchBatch, Notification
from app.db.session import SessionLocal
from app.services import lifecycle, match_orchestrator, notification_service

logger = get_logger(__name__)

_stop = threading.Event()
_last_cleanup: float = 0.0


def run_once(db: Session | None = None) -> dict[str, int]:
    own = db is None
    session = db or SessionLocal()
    try:
        processed = match_orchestrator.process_processing_batches(session, limit=5)
        expired = lifecycle.expire(session)
        archived = lifecycle.archive(session)
        delivered = notification_service.deliver_pending(session, limit=50)
        _remind_expiring(session)
        cleaned = {"notifications": 0, "disclosure_logs": 0, "rate_counters": 0}
        global _last_cleanup
        if time.time() - _last_cleanup >= 86400:
            cleaned = lifecycle.cleanup(session)
            _last_cleanup = time.time()
        session.commit()
        return {
            "processed": processed,
            "expired": expired,
            "archived": archived,
            "delivered": delivered,
            **{f"cleaned_{key}": value for key, value in cleaned.items()},
        }
    finally:
        if own:
            session.close()


def _remind_expiring(db: Session) -> int:
    soon = utcnow() + timedelta(hours=1)
    rows = db.execute(
        select(MatchBatch).where(
            MatchBatch.status.in_(
                [BatchStatus.completed.value, BatchStatus.degraded_completed.value]
            ),
            MatchBatch.expires_at.is_not(None),
            MatchBatch.expires_at <= soon,
            MatchBatch.expires_at > utcnow(),
        )
    ).scalars().all()
    reminded = 0
    for batch in rows:
        exists = db.execute(
            select(Notification.id).where(
                Notification.user_id == batch.initiator_id,
                Notification.type == "candidate_expiring",
                Notification.ref_type == "match_batch",
                Notification.ref_id == batch.id,
            )
        ).scalar_one_or_none()
        if exists is None:
            notification_service.notify(
                db,
                user_id=batch.initiator_id,
                event_type="candidate_expiring",
                ref_type="match_batch",
                ref_id=batch.id,
            )
            reminded += 1
    return reminded


def _loop() -> None:
    while not _stop.is_set():
        try:
            run_once()
        except Exception:  # noqa: BLE001
            logger.exception("scheduler tick failed")
        _stop.wait(settings.match_job_scan_seconds)


def start_scheduler() -> threading.Thread | None:
    if not settings.background_jobs_enabled:
        logger.info("background jobs disabled")
        return None
    _stop.clear()
    thread = threading.Thread(target=_loop, name="findstar-jobs", daemon=True)
    thread.start()
    logger.info("background jobs started")
    return thread


def stop_scheduler() -> None:
    _stop.set()