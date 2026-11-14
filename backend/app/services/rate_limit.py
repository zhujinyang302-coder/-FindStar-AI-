"""频控权威计数（匹配第 4 层 / FR-308）。

数据库为权威，窗口按自然日；Redis 仅可作为前置加速。
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.response import RateLimitError
from app.core.timeutil import utcnow
from app.db.enums import RateLimitAction
from app.db.models import RateLimitCounter

_LIMITS: dict[str, int] = {
    RateLimitAction.match_request.value: settings.match_user_daily_limit,
    RateLimitAction.view_candidate.value: settings.view_user_daily_limit,
    RateLimitAction.view_summary.value: settings.view_batch_daily_limit,
    RateLimitAction.contact_submit.value: settings.contact_daily_limit,
    RateLimitAction.view_batch.value: settings.view_user_daily_limit,
    RateLimitAction.item_create.value: settings.item_create_daily_limit,
}


def _window() -> str:
    return utcnow().strftime("%Y-%m-%d")


def limit_for(action: str) -> int:
    if action == RateLimitAction.item_create.value:
        return settings.item_create_daily_limit
    return _LIMITS.get(action, settings.match_user_daily_limit)


def check_and_increment(
    db: Session,
    *,
    subject_type: str,
    subject_id: int | str,
    action: str,
    limit: int | None = None,
) -> None:
    """原子递增；超限抛 429。调用方负责提交事务。"""
    cap = limit if limit is not None else limit_for(action)
    window = _window()
    result = db.execute(
        update(RateLimitCounter)
        .where(
            RateLimitCounter.subject_type == subject_type,
            RateLimitCounter.subject_id == str(subject_id),
            RateLimitCounter.action == action,
            RateLimitCounter.window_start == window,
            RateLimitCounter.count < cap,
        )
        .values(count=RateLimitCounter.count + 1)
    )
    if result.rowcount:
        return
    row = db.execute(
        select(RateLimitCounter).where(
            RateLimitCounter.subject_type == subject_type,
            RateLimitCounter.subject_id == str(subject_id),
            RateLimitCounter.action == action,
            RateLimitCounter.window_start == window,
        )
    ).scalars().first()
    if row is not None:
        raise RateLimitError("今日操作次数已达上限，请明日再试")
    db.add(
        RateLimitCounter(
            subject_type=subject_type,
            subject_id=str(subject_id),
            action=action,
            window_start=window,
            count=1,
        )
    )
    db.flush()


def current_count(
    db: Session, *, subject_type: str, subject_id: int | str, action: str
) -> int:
    row = db.execute(
        select(RateLimitCounter).where(
            RateLimitCounter.subject_type == subject_type,
            RateLimitCounter.subject_id == str(subject_id),
            RateLimitCounter.action == action,
            RateLimitCounter.window_start == _window(),
        )
    ).scalars().first()
    return int(row.count) if row else 0