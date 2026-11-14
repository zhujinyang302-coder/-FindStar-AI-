"""站内通知服务。

通知与业务同事务写 outbox（delivery_status=pending），投递失败不影响主流程。
正文只含事件类型、状态与"请登录查看"，不含候选标题/描述/图片/分数/身份/私密核验。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.db.models import Notification, User
from app.db.enums import NotificationType

_RETENTION_DAYS = 90

_PHONE = re.compile(r"1[3-9]\d{9}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_QQ_WECHAT = re.compile(r"(?:QQ|微信|wx|wechat|VX|vx)\s*[:：]?\s*[A-Za-z0-9_-]{5,}")
_ID_CARD = re.compile(r"\b\d{17}[\dXx]\b")

_TEMPLATES: dict[str, tuple[str, str]] = {
    NotificationType.match_completed.value: ("匹配完成", "已生成候选，请登录查看。"),
    NotificationType.match_no_candidate.value: ("暂无可靠候选", "本次匹配暂无可靠候选，请登录查看。"),
    NotificationType.match_degraded.value: ("匹配已降级完成", "匹配服务降级，结果可能不完整，请登录查看。"),
    NotificationType.candidate_expiring.value: ("候选即将过期", "你的匹配候选即将过期，请登录查看。"),
    NotificationType.candidate_expired.value: ("候选已过期", "匹配候选已过期，请重新发起匹配。"),
    NotificationType.contact_received.value: ("收到一条申请", "你收到一条联系申请，请登录查看。"),
    NotificationType.contact_confirmed.value: ("申请已确认", "你的申请已确认，请登录查看交接信息。"),
    NotificationType.contact_rejected.value: ("申请未通过", "你的申请未通过，请登录查看。"),
    NotificationType.contact_cooldown.value: ("申请暂时受限", "申请失败次数较多，暂时无法再次提交。"),
    NotificationType.review_result.value: ("审核结果", "你的记录审核状态已更新，请登录查看。"),
    NotificationType.listing_auto_approved.value: (
        "记录已上架",
        "已自动通过，匹配任务已受理，请登录查看。",
    ),
    NotificationType.admin_delisted.value: (
        "记录已被下架",
        "记录已被管理员下架，请登录查看。",
    ),
}


def sanitize_notification_text(text: str) -> str:
    text = _PHONE.sub("***", text or "")
    text = _EMAIL.sub("***", text)
    text = _QQ_WECHAT.sub("***", text)
    text = _ID_CARD.sub("***", text)
    return text


def notify(
    db: Session,
    *,
    user_id: int,
    event_type: str,
    ref_type: str | None = None,
    ref_id: int | None = None,
    body: str | None = None,
) -> Notification:
    title, default_body = _TEMPLATES.get(
        event_type, ("站内通知", "有新的消息，请登录查看。")
    )
    notification = Notification(
        user_id=user_id,
        type=event_type,
        title=sanitize_notification_text(title),
        body=sanitize_notification_text(body or default_body),
        ref_type=ref_type,
        ref_id=ref_id,
        is_read=False,
        delivery_status="pending",
        created_at=utcnow(),
    )
    db.add(notification)
    return notification


def list_notifications(
    db: Session, *, user_id: int, page: int = 1, page_size: int = 20
) -> tuple[list[Notification], int, int]:
    cutoff = utcnow().timestamp() - _RETENTION_DAYS * 86400
    rows = db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
    ).scalars().all()
    visible = [row for row in rows if row.created_at.timestamp() >= cutoff]
    start = (page - 1) * page_size
    unread = len([row for row in visible if not row.is_read])
    return visible[start : start + page_size], len(visible), unread


def unread_count(db: Session, *, user_id: int) -> int:
    return int(
        db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        ).scalar_one()
    )


def mark_read(db: Session, *, user_id: int, notification_id: int) -> bool:
    row = db.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
    ).scalars().first()
    if row is None:
        return False
    if not row.is_read:
        row.is_read = True
        db.flush()
    return True


def mark_all_read(db: Session, *, user_id: int) -> int:
    rows = db.execute(
        select(Notification).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
    ).scalars().all()
    for row in rows:
        row.is_read = True
    db.flush()
    return len(rows)


def deliver_pending(db: Session, *, limit: int = 50) -> int:
    """outbox 投递：最多 3 次，接收人停用则 skipped。失败不阻断业务。"""
    rows = db.execute(
        select(Notification)
        .where(Notification.delivery_status == "pending")
        .order_by(Notification.created_at.asc())
        .limit(limit)
    ).scalars().all()
    delivered = 0
    for row in rows:
        user = db.get(User, row.user_id)
        if user is None or user.status != "active":
            row.delivery_status = "skipped"
            continue
        row.attempts += 1
        # 站内通知落库即视为可读；此处保留通道重试语义。
        row.delivery_status = "sent"
        row.delivered_at = utcnow()
        delivered += 1
    db.flush()
    return delivered


def notification_payload(row: Notification) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "body": row.body,
        "ref_type": row.ref_type,
        "ref_id": row.ref_id,
        "is_read": row.is_read,
        "created_at": row.created_at,
    }