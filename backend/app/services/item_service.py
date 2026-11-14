"""记录（寻物/拾获）业务服务（V3）。

发布即待审；本人记录全状态可见；任何对侧信息不进入本模块输出。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.listing_modes import (
    AUDIT_ITEM_AUTO_APPROVED,
    AUTO_APPROVAL_OPINION,
    AUTO_APPROVAL_SOURCE,
    NOTIFICATION_LISTING_AUTO_APPROVED,
    OWNER_REQUEST_SOURCE,
    current_review_mode,
    is_auto_mode,
)
from app.core.response import BusinessError, ConflictError, NotFoundError, ValidationError
from app.core.timeutil import utcnow
from app.db.enums import (
    BatchStatus,
    ContactStatus,
    ItemLifecycleStatus as S,
    ItemType,
    ReviewTicketStatus,
    ReviewType,
    VisibilityScope,
)
from app.db.models import (
    ContactRequest,
    FoundItem,
    ItemImage,
    LostItem,
    MatchBatch,
    ReviewTicket,
    User,
)
from app.schemas.item import (
    ContactSummaryOut,
    ImageOut,
    ItemListItem,
    ItemListOut,
    ItemOut,
    LatestReviewOut,
    MatchSummaryOut,
    MyItemDetailOut,
    MyItemListItem,
    MyItemListOut,
    MyItemOut,
    normalize_location_code,
)

_ITEM_MODELS: dict[str, type[LostItem] | type[FoundItem]] = {
    ItemType.lost.value: LostItem,
    ItemType.found.value: FoundItem,
}

_TIME_FIELD = {ItemType.lost.value: "lost_at", ItemType.found.value: "found_at"}

_IMAGE_URL = "/api/v1/images/{key}"

_EDITABLE = {
    S.pending_listing.value,
    S.listing_rejected.value,
    S.active.value,
    S.delisted.value,
}


def _model(item_type: str) -> type[LostItem] | type[FoundItem]:
    model = _ITEM_MODELS.get(item_type)
    if model is None:
        raise ValidationError(f"未知的记录类型：{item_type}")
    return model


def image_url(object_key: str) -> str:
    return _IMAGE_URL.format(key=object_key)


# ---------------- 创建 ----------------
def _validate_image_keys(db: Session, image_keys: list[str]) -> None:
    if len(image_keys) > settings.max_images_per_item:
        raise ValidationError(f"单条记录最多 {settings.max_images_per_item} 张图片")
    from app.services.image_service import stat_image

    for key in image_keys:
        try:
            stat_image(key)
        except Exception as exc:  # noqa: BLE001
            raise BusinessError(
                f"图片标识不合法：{key}", code="INVALID_IMAGE_KEY", status_code=422
            ) from exc
        used = db.execute(
            select(ItemImage.id).where(ItemImage.object_key == key)
        ).scalar_one_or_none()
        if used is not None:
            raise BusinessError(
                "图片已被其他记录引用", code="INVALID_IMAGE_KEY", status_code=422
            )


def _risk_label(risk: Any) -> str:
    if risk.blocked:
        return "blocked"
    if risk.error:
        return "error"
    if risk.soft:
        return "soft"
    return "none"


def create_item(
    db: Session, *, user: User, item_type: str, payload: Any
) -> tuple[Any, ReviewTicket]:
    if not payload.matching_notice_accepted:
        raise BusinessError(
            "首次上传需确认匹配告知", code="NOTICE_NOT_ACCEPTED", status_code=422
        )
    if not payload.info_sufficient:
        raise BusinessError(
            "请至少上传 1 张图片或填写不少于 20 字的描述",
            code="INSUFFICIENT_INFO",
            status_code=422,
            details=[{"field": "description", "message": "信息不足，无法进行匹配"}],
        )
    image_keys: list[str] = list(payload.image_keys or [])
    _validate_image_keys(db, image_keys)

    from app.services import listing_policy, security_service

    risk = listing_policy.precheck(
        title=payload.title, description=payload.description
    )
    if risk.blocked:
        actor_id = user.id
        db.rollback()
        security_service.record_event(
            db,
            actor_id=actor_id,
            event_type="listing_risk_blocked",
            detail={"item_type": item_type, "title_len": len(payload.title)},
        )
        db.commit()
        raise BusinessError(
            "内容包含不允许发布的信息",
            code="CONTENT_RISK_BLOCKED",
            status_code=422,
        )

    model = _model(item_type)
    item = model(
        user_id=user.id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        color=payload.color,
        brand=payload.brand,
        location_code=normalize_location_code(payload.location_code),
        location_text=payload.location_text,
        status=S.pending_listing.value,
        is_removed=False,
        visibility_scope=VisibilityScope.owner_only.value,
        info_sufficient=payload.info_sufficient,
        data_version=1,
        review_round=1,
        **{_TIME_FIELD[item_type]: payload.occurred_at},
    )
    db.add(item)
    db.flush()

    _attach_images(db, item_type=item_type, item_id=item.id, image_keys=image_keys)

    auto = is_auto_mode()
    if auto:
        item.status = S.active.value
        item.visibility_scope = VisibilityScope.match_disclosure.value

    from app.services.review_service import create_ticket

    ticket = create_ticket(
        db,
        review_type=ReviewType.listing.value,
        item_type=item_type,
        item_id=item.id,
        applicant_id=user.id,
        review_round=1,
        source=AUTO_APPROVAL_SOURCE if auto else OWNER_REQUEST_SOURCE,
        status=(
            ReviewTicketStatus.approved.value
            if auto
            else ReviewTicketStatus.pending.value
        ),
        opinion=AUTO_APPROVAL_OPINION if auto else None,
        decided_at=utcnow() if auto else None,
    )
    item.latest_ticket_id = ticket.id

    sampled = listing_policy.is_sampled(item_type, item.id, risk)
    from app.services import audit, notification_service

    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="item_submit",
        entity_type=f"{item_type}_item",
        entity_id=item.id,
        after_status=item.status,
        details={
            "ticket_no": ticket.ticket_no,
            "review_mode": current_review_mode(),
            "risk": _risk_label(risk),
            "sampled": sampled,
        },
    )
    if auto:
        audit.record_audit(
            db,
            actor_id=None,
            actor_role="system",
            action=AUDIT_ITEM_AUTO_APPROVED,
            entity_type=f"{item_type}_item",
            entity_id=item.id,
            before_status=S.pending_listing.value,
            after_status=S.active.value,
            reason=AUTO_APPROVAL_OPINION,
            details={
                "ticket_no": ticket.ticket_no,
                "review_mode": current_review_mode(),
                "sampled": sampled,
            },
        )
        notification_service.notify(
            db,
            user_id=user.id,
            event_type=NOTIFICATION_LISTING_AUTO_APPROVED,
            ref_type="review_ticket",
            ref_id=ticket.id,
        )
        if risk.soft or risk.error:
            security_service.record_event(
                db,
                actor_id=user.id,
                event_type="listing_risk_soft" if risk.soft else "listing_risk_error",
                detail={
                    "item_type": item_type,
                    "item_id": item.id,
                    "sampled": True,
                },
            )
        elif sampled:
            security_service.record_event(
                db,
                actor_id=user.id,
                event_type="listing_sampled",
                detail={
                    "item_type": item_type,
                    "item_id": item.id,
                    "sampled": True,
                },
            )
        if settings.auto_match_on_approve and item.info_sufficient:
            from app.services.match_orchestrator import enqueue_auto_match

            enqueue_auto_match(
                db,
                item_type=item_type,
                item=item,
                initiator_id=user.id,
            )
    else:
        notification_service.notify(
            db,
            user_id=user.id,
            event_type="review_result",
            ref_type="review_ticket",
            ref_id=ticket.id,
        )
    db.flush()
    return item, ticket


def _attach_images(
    db: Session, *, item_type: str, item_id: int, image_keys: list[str]
) -> None:
    from app.services.image_service import stat_image

    for key in image_keys:
        mime, size = stat_image(key)
        db.add(
            ItemImage(
                item_type=item_type,
                item_id=item_id,
                object_key=key,
                mime_type=mime,
                size_bytes=size,
            )
        )


def _stat_image(object_key: str) -> tuple[str, int]:
    from app.services.image_service import stat_image

    return stat_image(object_key)


# ---------------- 本人记录 ----------------
def list_my_items(
    db: Session,
    *,
    user: User,
    item_type: str | None,
    status: str | None,
    has_match: bool | None,
    page: int,
    page_size: int,
) -> MyItemListOut:
    types = [item_type] if item_type in _ITEM_MODELS else list(_ITEM_MODELS.keys())
    rows: list[tuple[str, Any]] = []
    for current_type in types:
        model = _model(current_type)
        stmt = select(model).where(model.user_id == user.id)
        if status:
            stmt = stmt.where(model.status == status)
        rows.extend(
            (current_type, row) for row in db.execute(stmt).scalars().all()
        )
    rows.sort(key=lambda pair: pair[1].updated_at, reverse=True)

    items = [
        _serialize_my_list_item(db, row, current_type, user)
        for current_type, row in rows
    ]
    if has_match is not None:
        items = [item for item in items if bool(item.match_summary) is has_match]
    total = len(items)
    start = (page - 1) * page_size
    return MyItemListOut(
        items=items[start : start + page_size], total=total, page=page, page_size=page_size
    )


def get_item(db: Session, item_type: str, item_id: int) -> Any:
    model = _model(item_type)
    item = db.get(model, item_id)
    if item is None:
        raise NotFoundError("记录不存在")
    return item


def get_my_item(db: Session, *, user: User, item_type: str, item_id: int) -> Any:
    item = get_item(db, item_type, item_id)
    if item.user_id != user.id:
        raise NotFoundError("记录不存在")
    return item


def get_my_item_detail(
    db: Session, *, user: User, item_type: str, item_id: int
) -> MyItemDetailOut:
    item = get_my_item(db, user=user, item_type=item_type, item_id=item_id)
    return _serialize_my_detail(db, item, item_type, user)


def update_item(
    db: Session, *, user: User, item_type: str, item_id: int, payload: Any
) -> tuple[Any, ReviewTicket]:
    item = get_my_item(db, user=user, item_type=item_type, item_id=item_id)
    if item.status not in _EDITABLE or item.is_removed:
        raise ConflictError("记录当前状态不允许编辑", code="ITEM_NOT_EDITABLE")

    data = payload.model_dump(exclude_unset=True)
    image_keys = data.pop("image_keys", None)
    if "occurred_at" in data:
        setattr(item, _TIME_FIELD[item_type], data.pop("occurred_at"))
    if "location_code" in data:
        data["location_code"] = normalize_location_code(data["location_code"])
    for field_name, value in data.items():
        setattr(item, field_name, value)

    if image_keys is not None:
        _validate_image_keys(db, list(image_keys))
        db.execute(
            ItemImage.__table__.delete().where(
                ItemImage.item_type == item_type, ItemImage.item_id == item.id
            )
        )
        _attach_images(db, item_type=item_type, item_id=item.id, image_keys=list(image_keys))

    description = item.description or ""
    item.info_sufficient = bool(
        db.execute(
            select(ItemImage.id).where(
                ItemImage.item_type == item_type, ItemImage.item_id == item.id
            )
        ).first()
    ) or len(description.strip()) >= 20

    auto = is_auto_mode()
    if auto and not item.info_sufficient:
        raise BusinessError(
            "请至少上传 1 张图片或填写不少于 20 字的描述",
            code="INSUFFICIENT_INFO",
            status_code=422,
            details=[{"field": "description", "message": "信息不足，无法进行匹配"}],
        )

    before = item.status
    item.data_version = int(item.data_version or 0) + 1
    item.review_round = int(item.review_round or 1) + 1
    if auto:
        from app.services.state_machine import assert_transition

        if before != S.active.value:
            assert_transition(before, S.active.value)
        item.status = S.active.value
        item.visibility_scope = VisibilityScope.match_disclosure.value
    else:
        item.status = S.pending_listing.value
        item.visibility_scope = VisibilityScope.owner_only.value

    # 取消旧待审单
    db.execute(
        ReviewTicket.__table__.update()
        .where(
            ReviewTicket.item_type == item_type,
            ReviewTicket.item_id == item.id,
            ReviewTicket.review_type == ReviewType.listing.value,
            ReviewTicket.status == ReviewTicketStatus.pending.value,
        )
        .values(status=ReviewTicketStatus.cancelled.value)
    )

    from app.services.review_service import create_ticket, invalidate_item_batches

    invalidate_item_batches(db, item_type, item.id)
    ticket = create_ticket(
        db,
        review_type=ReviewType.listing.value,
        item_type=item_type,
        item_id=item.id,
        applicant_id=user.id,
        review_round=item.review_round,
        source=AUTO_APPROVAL_SOURCE if auto else OWNER_REQUEST_SOURCE,
        status=(
            ReviewTicketStatus.approved.value
            if auto
            else ReviewTicketStatus.pending.value
        ),
        opinion=AUTO_APPROVAL_OPINION if auto else None,
        decided_at=utcnow() if auto else None,
    )
    item.latest_ticket_id = ticket.id

    from app.services import audit, notification_service

    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="item_update",
        entity_type=f"{item_type}_item",
        entity_id=item.id,
        before_status=before,
        after_status=item.status,
        details={
            "data_version": item.data_version,
            "ticket_no": ticket.ticket_no,
            "review_mode": current_review_mode(),
        },
    )
    if auto:
        notification_service.notify(
            db,
            user_id=user.id,
            event_type=NOTIFICATION_LISTING_AUTO_APPROVED,
            ref_type="review_ticket",
            ref_id=ticket.id,
        )
        if settings.auto_match_on_approve and item.info_sufficient:
            from app.services.match_orchestrator import enqueue_auto_match

            enqueue_auto_match(
                db,
                item_type=item_type,
                item=item,
                initiator_id=user.id,
            )
    else:
        notification_service.notify(
            db,
            user_id=user.id,
            event_type="review_result",
            ref_type="review_ticket",
            ref_id=ticket.id,
        )
    db.flush()
    return item, ticket


def withdraw(db: Session, *, user: User, item_type: str, item_id: int) -> dict:
    item = get_my_item(db, user=user, item_type=item_type, item_id=item_id)
    if item.status != S.pending_listing.value:
        raise ConflictError("仅待上架审核中的记录可撤回", code="ITEM_NOT_WITHDRAWABLE")
    before = item.status
    item.status = S.closed.value
    item.is_removed = True
    db.execute(
        ReviewTicket.__table__.update()
        .where(
            ReviewTicket.item_type == item_type,
            ReviewTicket.item_id == item.id,
            ReviewTicket.status == ReviewTicketStatus.pending.value,
        )
        .values(status=ReviewTicketStatus.cancelled.value)
    )
    from app.services.review_service import invalidate_item_batches
    from app.services import audit

    invalidate_item_batches(db, item_type, item.id)
    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="item_withdraw",
        entity_type=f"{item_type}_item",
        entity_id=item.id,
        before_status=before,
        after_status=item.status,
    )
    db.commit()
    return {"item_id": item.id, "status": item.status, "ticket_status": "cancelled"}


def resubmit(db: Session, *, user: User, item_type: str, item_id: int) -> dict:
    item = get_my_item(db, user=user, item_type=item_type, item_id=item_id)
    if item.status not in {S.listing_rejected.value, S.delisted.value}:
        raise ConflictError("当前状态不允许重新提交", code="ITEM_NOT_RESUBMITTABLE")
    auto = is_auto_mode()
    from app.services.state_machine import assert_transition

    before = item.status
    assert_transition(before, S.pending_listing.value)
    if auto:
        assert_transition(S.pending_listing.value, S.active.value)
    target = S.active.value if auto else S.pending_listing.value
    item.status = target
    item.is_removed = False
    item.review_round = int(item.review_round or 1) + 1
    item.data_version = int(item.data_version or 0) + 1
    if auto:
        item.visibility_scope = VisibilityScope.match_disclosure.value
    else:
        item.visibility_scope = VisibilityScope.owner_only.value
    from app.services.review_service import create_ticket, invalidate_item_batches
    from app.services import audit, notification_service

    invalidate_item_batches(db, item_type, item.id)
    ticket = create_ticket(
        db,
        review_type=ReviewType.listing.value,
        item_type=item_type,
        item_id=item.id,
        applicant_id=user.id,
        review_round=item.review_round,
        source=AUTO_APPROVAL_SOURCE if auto else OWNER_REQUEST_SOURCE,
        status=(
            ReviewTicketStatus.approved.value
            if auto
            else ReviewTicketStatus.pending.value
        ),
        opinion=AUTO_APPROVAL_OPINION if auto else None,
        decided_at=utcnow() if auto else None,
    )
    item.latest_ticket_id = ticket.id
    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="item_resubmit",
        entity_type=f"{item_type}_item",
        entity_id=item.id,
        before_status=before,
        after_status=item.status,
        details={
            "ticket_no": ticket.ticket_no,
            "review_mode": current_review_mode(),
        },
    )
    if auto:
        notification_service.notify(
            db,
            user_id=user.id,
            event_type=NOTIFICATION_LISTING_AUTO_APPROVED,
            ref_type="review_ticket",
            ref_id=ticket.id,
        )
        if settings.auto_match_on_approve and item.info_sufficient:
            from app.services.match_orchestrator import enqueue_auto_match

            enqueue_auto_match(
                db,
                item_type=item_type,
                item=item,
                initiator_id=user.id,
            )
    else:
        notification_service.notify(
            db,
            user_id=user.id,
            event_type="review_result",
            ref_type="review_ticket",
            ref_id=ticket.id,
        )
    db.flush()
    return {
        "item_id": item.id,
        "status": item.status,
        "review_ticket_no": ticket.ticket_no,
    }


# ---------------- 序列化（白名单） ----------------
def _owner_nickname(db: Session, user_id: int) -> str:
    user = db.get(User, user_id)
    return user.nickname if user else "匿名用户"


def serialize_images(images: list[ItemImage]) -> list[ImageOut]:
    return [
        ImageOut(
            id=img.id,
            object_key=img.object_key,
            url=image_url(img.object_key),
            mime_type=img.mime_type,
            size_bytes=img.size_bytes,
        )
        for img in images
    ]


def serialize_list_item(item: Any, item_type: str) -> ItemListItem:
    images = getattr(item, "images", []) or []
    cover = image_url(images[0].object_key) if images else None
    return ItemListItem(
        id=item.id,
        type=item_type,
        title=item.title,
        category=item.category,
        color=item.color,
        location_text=item.location_text,
        occurred_at=getattr(item, _TIME_FIELD[item_type]),
        status=item.status,
        created_at=item.created_at,
        cover_image=cover,
    )


def serialize_item(
    db: Session, item: Any, item_type: str, *, viewer_id: int | None
) -> ItemOut:
    """旧链接兼容输出：仅发布者本人可读。"""
    images = getattr(item, "images", []) or []
    is_owner = viewer_id is not None and item.user_id == viewer_id
    return ItemOut(
        id=item.id,
        type=item_type,
        title=item.title,
        description=item.description,
        category=item.category,
        color=item.color,
        brand=item.brand,
        location_code=item.location_code,
        location_text=item.location_text,
        occurred_at=getattr(item, _TIME_FIELD[item_type]),
        status=item.status,
        owner_nickname=_owner_nickname(db, item.user_id),
        is_owner=is_owner,
        can_claim=False,
        created_at=item.created_at,
        images=serialize_images(images),
    )


def _latest_review(db: Session, item: Any, item_type: str) -> LatestReviewOut | None:
    ticket = db.execute(
        select(ReviewTicket)
        .where(
            ReviewTicket.item_type == item_type,
            ReviewTicket.item_id == item.id,
        )
        .order_by(ReviewTicket.created_at.desc())
    ).scalars().first()
    if ticket is None:
        return None
    return LatestReviewOut(
        status=ticket.status, opinion=ticket.opinion, decided_at=ticket.decided_at
    )


def _match_summary(db: Session, item: Any, item_type: str) -> MatchSummaryOut | None:
    batch = db.execute(
        select(MatchBatch)
        .where(
            MatchBatch.initiated_item_type == item_type,
            MatchBatch.initiated_item_id == item.id,
        )
        .order_by(MatchBatch.created_at.desc())
    ).scalars().first()
    if batch is None:
        return None
    return MatchSummaryOut(
        last_batch_id=batch.batch_id,
        candidate_count=batch.candidate_count,
        degraded=batch.degraded,
        expires_at=batch.expires_at,
    )


def _contact_summary(db: Session, item: Any, item_type: str) -> ContactSummaryOut:
    count = db.execute(
        select(func.count(ContactRequest.id)).where(
            ContactRequest.target_item_type == item_type,
            ContactRequest.target_item_id == item.id,
            ContactRequest.status == ContactStatus.pending.value,
        )
    ).scalar_one()
    return ContactSummaryOut(pending_received=int(count))


def _serialize_my_list_item(
    db: Session, item: Any, item_type: str, user: User
) -> MyItemListItem:
    images = getattr(item, "images", []) or []
    cover = image_url(images[0].object_key) if images else None
    return MyItemListItem(
        id=item.id,
        type=item_type,
        title=item.title,
        category=item.category,
        status=item.status,
        review_round=int(item.review_round or 1),
        latest_review=_latest_review(db, item, item_type),
        match_summary=_match_summary(db, item, item_type),
        contact_summary=_contact_summary(db, item, item_type),
        cover_image=cover,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _serialize_my_detail(
    db: Session, item: Any, item_type: str, user: User
) -> MyItemDetailOut:
    from app.services.visibility_policy import can_initiate_match

    status = item.status
    return MyItemDetailOut(
        id=item.id,
        type=item_type,
        title=item.title,
        description=item.description,
        category=item.category,
        color=item.color,
        brand=item.brand,
        location_code=item.location_code,
        location_text=item.location_text,
        occurred_at=getattr(item, _TIME_FIELD[item_type]),
        status=status,
        info_sufficient=bool(item.info_sufficient),
        review_round=int(item.review_round or 1),
        can_match=can_initiate_match(status) and bool(item.info_sufficient),
        can_edit=status in _EDITABLE and not item.is_removed,
        can_withdraw=status == S.pending_listing.value,
        can_request_delist=status in {S.active.value, S.claimed.value},
        latest_review=_latest_review(db, item, item_type),
        images=serialize_images(list(getattr(item, "images", []) or [])),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def serialize_my_item(item: Any, item_type: str, ticket_no: str | None) -> MyItemOut:
    return MyItemOut(
        id=item.id,
        type=item_type,
        status=item.status,
        info_sufficient=bool(item.info_sufficient),
        review_ticket_no=ticket_no,
        data_version=int(item.data_version or 1),
        created_at=item.created_at,
    )


def to_side(item: Any, item_type: str) -> "Any":
    """把 ORM 记录转换为评分用的 ItemSide 快照。"""
    from app.ai.matching import ItemSide

    return ItemSide(
        title=item.title,
        description=item.description,
        category=item.category,
        color=item.color,
        brand=item.brand,
        location_code=item.location_code,
        location_text=item.location_text,
        occurred_at=getattr(item, _TIME_FIELD[item_type]),
        features=item.features,
    )