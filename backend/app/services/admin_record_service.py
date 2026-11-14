"""管理端记录总览、详情与直接下架服务。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.response import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.timeutil import utcnow
from app.db.enums import (
    ItemLifecycleStatus as S,
    ReviewTicketStatus,
    ReviewType,
    SENSITIVE_CATEGORIES,
    UserRole,
)
from app.db.models import (
    FoundItem,
    ItemImage,
    LostItem,
    ReviewTicket,
    User,
)
from app.schemas.admin_records import (
    AdminRecordDetailOut,
    AdminRecordImage,
    AdminRecordListItem,
    AdminRecordListOut,
    AdminReviewBrief,
    AdminDelistOut,
)
from app.services import audit, notification_service, review_service

_MODELS = (("lost", LostItem), ("found", FoundItem))


def _model(item_type: str):
    for name, model in _MODELS:
        if name == item_type:
            return model
    raise ValidationError("未知的记录类型")


def _image_url(key: str | None) -> str | None:
    return f"/api/v1/images/{key}" if key else None


def list_records(
    db: Session,
    *,
    item_type: str,
    status: str,
    created_from: datetime | None,
    created_to: datetime | None,
    keyword: str | None,
    page: int,
    page_size: int,
) -> AdminRecordListOut:
    rows: list[tuple[str, object]] = []
    for name, model in _MODELS:
        if item_type != "all" and name != item_type:
            continue
        stmt = select(model)
        if status and status != "all":
            stmt = stmt.where(model.status == status)
        else:
            stmt = stmt.where(
                model.status.in_([S.active.value, S.delisting_review.value])
            )
        if keyword:
            stmt = stmt.where(model.title.like(f"%{keyword}%"))
        if created_from:
            stmt = stmt.where(model.created_at >= created_from)
        if created_to:
            stmt = stmt.where(model.created_at <= created_to)
        rows.extend((name, item) for item in db.execute(stmt).scalars().all())

    rows.sort(key=lambda pair: pair[1].created_at, reverse=True)
    total = len(rows)
    start = (page - 1) * page_size
    items = []
    for name, item in rows[start : start + page_size]:
        pending = db.execute(
            select(ReviewTicket.id).where(
                ReviewTicket.review_type == ReviewType.delisting.value,
                ReviewTicket.item_type == name,
                ReviewTicket.item_id == item.id,
                ReviewTicket.status == ReviewTicketStatus.pending.value,
            )
        ).first()
        items.append(
            AdminRecordListItem(
                item_type=name,
                item_id=item.id,
                title=item.title,
                category=item.category,
                color=item.color,
                location_text=item.location_text,
                occurred_at=getattr(item, f"{name}_at"),
                status=item.status,
                created_at=item.created_at,
                is_removed=bool(item.is_removed),
                has_pending_delist=pending is not None,
            )
        )
    return AdminRecordListOut(
        items=items, total=total, page=page, page_size=page_size
    )


def get_record(
    db: Session, *, admin: User, item_type: str, item_id: int
) -> AdminRecordDetailOut:
    if admin.role != UserRole.admin.value:
        raise ForbiddenError("需要管理员权限")
    model = _model(item_type)
    item = db.get(model, item_id)
    if item is None:
        raise NotFoundError("记录不存在")

    from app.services import disclosure_policy

    sensitive = item.category in SENSITIVE_CATEGORIES
    images = []
    for image in db.execute(
        select(ItemImage)
        .where(ItemImage.item_type == item_type, ItemImage.item_id == item.id)
        .order_by(ItemImage.id.asc())
    ).scalars().all():
        images.append(
            AdminRecordImage(
                id=image.id,
                url=None if sensitive else _image_url(image.object_key),
                thumb_url=_image_url(image.thumb_key or image.object_key),
                sensitive_masked=bool(sensitive or image.sensitive_masked),
            )
        )

    history = [
        AdminReviewBrief(
            review_round=row.review_round,
            status=row.status,
            opinion=row.opinion,
            decided_at=row.decided_at,
        )
        for row in db.execute(
            select(ReviewTicket)
            .where(
                ReviewTicket.item_type == item_type,
                ReviewTicket.item_id == item.id,
            )
            .order_by(ReviewTicket.created_at.asc())
        ).scalars().all()
    ]

    audit.record_audit(
        db,
        actor_id=admin.id,
        actor_role=admin.role,
        action="admin_record_viewed",
        entity_type=f"{item_type}_item",
        entity_id=item.id,
        details={"item_type": item_type},
    )
    db.flush()

    return AdminRecordDetailOut(
        item_type=item_type,
        item_id=item.id,
        title=item.title,
        category=item.category,
        color=item.color,
        brand=item.brand,
        location_text=item.location_text,
        location_code=item.location_code,
        occurred_at=getattr(item, f"{item_type}_at"),
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
        info_sufficient=bool(item.info_sufficient),
        review_round=int(item.review_round or 1),
        description=disclosure_policy.sanitize_disclosure_text(
            item.description or ""
        ),
        images=images,
        history=history,
    )


def direct_delist(
    db: Session, *, admin: User, item_type: str, item_id: int, reason: str
) -> AdminDelistOut:
    if admin.role != UserRole.admin.value:
        raise ForbiddenError("需要管理员权限")
    if not settings.admin_direct_delist_enabled:
        raise ForbiddenError("管理员直接下架已关闭", code="ADMIN_DIRECT_DISABLED")
    model = _model(item_type)
    item = db.get(model, item_id)
    if item is None:
        raise NotFoundError("记录不存在")
    if item.user_id == admin.id:
        raise ForbiddenError("不得下架本人记录", code="SELF_REVIEW_FORBIDDEN")
    if item.status in {S.claimed.value, S.resolved.value}:
        raise ConflictError("记录已完成，无法下架", code="ITEM_STATE_CHANGED")
    if item.status == S.delisted.value:
        raise ConflictError("记录已下架", code="ITEM_STATE_CHANGED")

    pending = db.execute(
        select(ReviewTicket).where(
            ReviewTicket.review_type == ReviewType.delisting.value,
            ReviewTicket.item_type == item_type,
            ReviewTicket.item_id == item.id,
            ReviewTicket.status == ReviewTicketStatus.pending.value,
        )
    ).scalars().first()
    if pending is not None:
        out = review_service.decide(
            db,
            admin=admin,
            ticket_no=pending.ticket_no,
            decision="approve",
            opinion=reason,
        )
        return AdminDelistOut(
            ticket_no=out.ticket_no,
            item_status=out.item_status,
            decided_at=out.decided_at,
            invalidated_batches=int(out.impact.get("invalidated_batches", 0)),
        )

    before = item.status
    item.status = S.delisted.value
    item.is_removed = True
    item.delisted_at = utcnow()
    ticket = review_service.create_ticket(
        db,
        review_type=ReviewType.delisting.value,
        item_type=item_type,
        item_id=item.id,
        applicant_id=None,
        review_round=int(item.review_round or 1),
        source="admin_direct",
        status=ReviewTicketStatus.approved.value,
        opinion=reason,
        decided_at=utcnow(),
    )
    ticket.decided_by = admin.id
    item.latest_ticket_id = ticket.id
    invalidated = review_service.invalidate_item_batches(db, item_type, item.id)

    audit.record_audit(
        db,
        actor_id=admin.id,
        actor_role=admin.role,
        action="admin_direct_delist",
        entity_type=f"{item_type}_item",
        entity_id=item.id,
        before_status=before,
        after_status=item.status,
        reason=reason,
        details={
            "invalidated_batches": invalidated,
            "ticket_no": ticket.ticket_no,
        },
    )
    notification_service.notify(
        db,
        user_id=item.user_id,
        event_type="admin_delisted",
        ref_type="review_ticket",
        ref_id=ticket.id,
        body="记录已被管理员下架，请登录查看。",
    )
    db.flush()
    return AdminDelistOut(
        ticket_no=ticket.ticket_no,
        item_status=item.status,
        decided_at=ticket.decided_at or utcnow(),
        invalidated_batches=invalidated,
    )