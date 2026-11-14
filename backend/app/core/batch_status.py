"""读取侧批次状态判定（单一来源）。

本模块只服务于读取裁决：批次详情、候选列表、单候选详情、候选解释。
不得将其用于写入侧的失效 / 过期集合——`lifecycle`、`contact_service`、
`review_service`、`expire()` 的集合语义不同，且包含 `processing`。
"""

from __future__ import annotations

from app.db.enums import BatchStatus

READABLE_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        BatchStatus.completed.value,
        BatchStatus.degraded_completed.value,
        BatchStatus.no_candidates.value,
    }
)

STATUS_MESSAGES: dict[str, str] = {
    BatchStatus.no_candidates.value: "暂无可靠候选",
    BatchStatus.degraded_completed.value: "匹配已降级完成，结果可能不完整",
}


def is_readable_terminal(status: str) -> bool:
    """批次是否处于可读取的终态。"""
    return status in READABLE_TERMINAL_STATUSES


def status_message(status: str) -> str | None:
    """批次状态对应的用户提示文案。"""
    return STATUS_MESSAGES.get(status)