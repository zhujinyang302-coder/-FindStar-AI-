"""物品状态机（V3 八态）。

状态集合：pending_listing、active、listing_rejected、delisting_review、
delisted、claimed、resolved、closed。
禁止非法转换；所有变更都必须经过本模块校验并写入审计日志。
"""

from __future__ import annotations

from app.core.response import ConflictError
from app.db.enums import ItemLifecycleStatus as S

# 合法转换表：当前状态 -> 允许到达的状态集合
LEGAL_TRANSITIONS: dict[str, set[str]] = {
    S.pending_listing.value: {S.active.value, S.listing_rejected.value, S.closed.value},
    S.active.value: {S.delisting_review.value, S.claimed.value, S.resolved.value, S.closed.value},
    S.delisting_review.value: {S.delisted.value, S.active.value},
    S.listing_rejected.value: {S.pending_listing.value, S.closed.value},
    S.delisted.value: {S.pending_listing.value, S.closed.value},
    S.claimed.value: {S.resolved.value, S.closed.value},
    S.resolved.value: {S.closed.value},
    S.closed.value: set(),
}

MATCHABLE_STATUSES: frozenset[str] = frozenset({S.active.value})
EXPOSED_STATUSES: frozenset[str] = frozenset(
    {S.active.value, S.delisting_review.value, S.claimed.value, S.resolved.value}
)


def can_transition(current: str, target: str) -> bool:
    if current == target:
        return True
    return target in LEGAL_TRANSITIONS.get(current, set())


def assert_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise ConflictError(f"非法状态转换：{current} → {target}", code="ILLEGAL_STATE_TRANSITION")


def ensure_status(status: str, allowed: set[str] | frozenset[str], message: str | None = None) -> None:
    if status not in allowed:
        raise ConflictError(message or "记录当前状态不允许该操作", code="ITEM_STATE_NOT_ALLOWED")


def ensure_active(status: str) -> None:
    """要求记录处于可操作（active）状态。"""
    ensure_status(status, MATCHABLE_STATUSES, "记录当前状态不允许该操作")


def matchable_statuses() -> frozenset[str]:
    return MATCHABLE_STATUSES