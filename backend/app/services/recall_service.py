"""硬约束过滤与候选池构建（匹配第 1 层）。

约束：同账号、类别冲突、时间窗口、方向时间语义、记录失效、历史已确认/已拒绝。
任一约束命中都不占用配额。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import ContactStatus, ItemLifecycleStatus, ItemType
from app.db.models import ContactRequest
from app.db.enums import UNKNOWN
from app.services.item_service import _TIME_FIELD, _model

_UNKNOWN_CATEGORIES = {UNKNOWN, "其他"}


@dataclass
class RecallResult:
    candidates: list[tuple[str, Any]] = field(default_factory=list)
    filter_stats: dict[str, int] = field(default_factory=dict)
    truncated: bool = False


def _occurred(item: Any, item_type: str):
    return getattr(item, _TIME_FIELD[item_type])


def _known_category(value: str | None) -> bool:
    return bool(value) and value not in _UNKNOWN_CATEGORIES


def _history_has_contact(
    db: Session, *, applicant_id: int, candidate_type: str, candidate_id: int
) -> bool:
    row = db.execute(
        select(ContactRequest.id).where(
            ContactRequest.applicant_id == applicant_id,
            ContactRequest.target_item_type == candidate_type,
            ContactRequest.target_item_id == candidate_id,
            ContactRequest.status.in_(
                [
                    ContactStatus.confirmed.value,
                    ContactStatus.rejected.value,
                    ContactStatus.closed.value,
                ]
            ),
        )
    ).scalar_one_or_none()
    return row is not None


def _time_closeness(a, b) -> float:
    if a is None or b is None:
        return 9999.0
    return abs((a - b).total_seconds()) / 86400.0


def build_candidate_pool(
    db: Session,
    *,
    initiated_item: Any,
    initiated_type: str,
    initiator_id: int | None = None,
    window_days: int,
    pool_max: int,
) -> RecallResult:
    candidate_type = (
        ItemType.found.value
        if initiated_type == ItemType.lost.value
        else ItemType.lost.value
    )
    model = _model(candidate_type)
    stats = {
        "same_user": 0,
        "category_conflict": 0,
        "time_window": 0,
        "time_direction": 0,
        "invalid_status": 0,
        "history_contact": 0,
    }

    rows = db.execute(
        select(model).where(
            model.is_removed.is_(False),
            model.status == ItemLifecycleStatus.active.value,
        )
    ).scalars().all()
    stats["invalid_status"] = 0

    kept: list[tuple[str, Any]] = []
    initiated_time = _occurred(initiated_item, initiated_type)
    for row in rows:
        if row.user_id == initiated_item.user_id:
            stats["same_user"] += 1
            continue
        if (
            _known_category(initiated_item.category)
            and _known_category(row.category)
            and initiated_item.category != row.category
        ):
            stats["category_conflict"] += 1
            continue
        candidate_time = _occurred(row, candidate_type)
        if initiated_time is not None and candidate_time is not None:
            if abs((candidate_time - initiated_time).days) > window_days:
                stats["time_window"] += 1
                continue
        if initiated_type == ItemType.lost.value:
            if (
                initiated_time is not None
                and candidate_time is not None
                and candidate_time < initiated_time - timedelta(days=1)
            ):
                stats["time_direction"] += 1
                continue
        else:
            if (
                initiated_time is not None
                and candidate_time is not None
                and candidate_time > initiated_time + timedelta(days=1)
            ):
                stats["time_direction"] += 1
                continue
        if initiator_id is not None and _history_has_contact(
            db,
            applicant_id=initiator_id,
            candidate_type=candidate_type,
            candidate_id=row.id,
        ):
            stats["history_contact"] += 1
            continue
        kept.append((candidate_type, row))

    truncated = False
    if len(kept) > pool_max:
        truncated = True
        kept.sort(
            key=lambda pair: (
                _time_closeness(initiated_time, _occurred(pair[1], candidate_type)),
                0 if pair[1].category == initiated_item.category else 1,
                pair[1].id,
            )
        )
        kept = kept[:pool_max]

    return RecallResult(candidates=kept, filter_stats=stats, truncated=truncated)