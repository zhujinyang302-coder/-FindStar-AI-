"""可见性唯一裁决（纯函数）。

所有 API 与序列化器只读本模块结果，禁止在其他位置直接比较 status。
矩阵来源：design.md 2.1.3（1）8×6 可见性裁决矩阵。
"""

from __future__ import annotations

from app.core.response import ForbiddenError, NotFoundError
from app.db.enums import ItemLifecycleStatus as S
from app.db.models import User

_STATUSES = tuple(item.value for item in S)

# 记录状态 -> (本人详情, 他人详情, 可入候选池, 可发起匹配, 可处理申请, 审核可见)
_MATRIX: dict[str, tuple[bool, bool, bool, bool, bool, bool]] = {
    S.pending_listing.value: (True, False, False, False, False, True),
    S.active.value: (True, False, True, True, True, True),
    S.listing_rejected.value: (True, False, False, False, False, True),
    S.delisting_review.value: (True, False, False, False, True, True),
    S.delisted.value: (True, False, False, False, False, True),
    S.claimed.value: (True, False, False, False, True, True),
    S.resolved.value: (True, False, False, False, False, True),
    S.closed.value: (True, False, False, False, False, True),
}


def _cell(status: str, index: int) -> bool:
    row = _MATRIX.get(status)
    return bool(row and row[index])


def can_view_own_detail(status: str) -> bool:
    return _cell(status, 0)


def can_view_other_detail(status: str) -> bool:
    return _cell(status, 1)


def can_join_candidate_pool(status: str) -> bool:
    return _cell(status, 2)


def can_initiate_match(status: str) -> bool:
    return _cell(status, 3)


def can_process_request(status: str) -> bool:
    return _cell(status, 4)


def can_review(status: str) -> bool:
    return _cell(status, 5)


def matrix_snapshot() -> dict[str, dict[str, bool]]:
    """返回可断言的矩阵快照（用于测试与文档核对）。"""
    return {
        status: {
            "own_detail": row[0],
            "other_detail": row[1],
            "candidate_pool": row[2],
            "initiate_match": row[3],
            "process_request": row[4],
            "review": row[5],
        }
        for status, row in _MATRIX.items()
    }


def assert_can_view_own_or_review(*, status: str, actor: User | None, owner_id: int) -> None:
    """通用详情访问裁决：发布者本人可读；管理员走审核详情；其他一律 404。"""
    if actor is not None and actor.id == owner_id and can_view_own_detail(status):
        return
    raise NotFoundError("记录不存在")


def assert_can_review(*, status: str) -> None:
    if not can_review(status):
        raise ForbiddenError("该记录不可审核", code="REVIEW_NOT_ALLOWED")


def assert_owner(actor: User, owner_id: int) -> None:
    if actor.id != owner_id:
        # 统一 404，避免泄露存在性
        raise NotFoundError("记录不存在")


def public_statistics_scope() -> frozenset[str]:
    """公开统计唯一允许的口径。"""
    return frozenset({"completed_total"})


def record_exposed(status: str, *, is_owner: bool) -> bool:
    """记录是否允许出现在任何面向他人的读取路径。"""
    return can_view_own_detail(status) if is_owner else can_view_other_detail(status)