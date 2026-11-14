"""我的记录接口：发布（发布即待审）、本人全状态读取、修改、撤回、重提、下架申请与上传。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.core.response import RateLimitError, ValidationError
from app.db.enums import ItemType, RateLimitAction, UserRole
from app.db.models import User
from app.db.session import get_db
from app.schemas.admin import DelistApplyRequest
from app.schemas.item import (
    FoundItemCreate,
    ItemUpdate,
    LostItemCreate,
    MyItemDetailOut,
    MyItemListOut,
    MyItemOut,
    WithdrawOut,
)
from app.services import idempotency, image_service, item_service, review_service

router = APIRouter(tags=["items"])
logger = get_logger(__name__)


def _require_user(user: User) -> User:
    if user.role == UserRole.admin.value:
        raise ValidationError("管理员不参与记录发布")
    return user


@router.post("/lost-items", response_model=MyItemOut, status_code=201)
def create_lost_item(
    payload: LostItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> MyItemOut:
    return _create(db, user, ItemType.lost.value, payload, idempotency_key)


@router.post("/found-items", response_model=MyItemOut, status_code=201)
def create_found_item(
    payload: FoundItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> MyItemOut:
    return _create(db, user, ItemType.found.value, payload, idempotency_key)


def _create(db: Session, user: User, item_type: str, payload, key: str | None) -> MyItemOut:
    _require_user(user)
    record, is_new = idempotency.begin(
        db, user_id=user.id, scope=f"create_{item_type}", key=key, payload=payload.model_dump()
    )
    cached = idempotency.cached_response(record)
    if not is_new and cached:
        return MyItemOut.model_validate(cached)
    from app.services import rate_limit

    try:
        with db.begin_nested():
            rate_limit.check_and_increment(
                db,
                subject_type="user",
                subject_id=user.id,
                action=RateLimitAction.item_create.value,
            )
    except RateLimitError:
        raise
    except Exception:  # noqa: BLE001
        logger.warning(
            "item create rate limit fail-open",
            extra={"error_category": "RATE_LIMIT_ERROR"},
        )
    item, ticket = item_service.create_item(
        db, user=user, item_type=item_type, payload=payload
    )
    out = item_service.serialize_my_item(item, item_type, ticket.ticket_no)
    idempotency.save_response(db, record, out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/my/items", response_model=MyItemListOut)
def list_my_items(
    type: str | None = Query(default=None, pattern="^(lost|found)$"),
    status: str | None = Query(default=None),
    has_match: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MyItemListOut:
    return item_service.list_my_items(
        db,
        user=user,
        item_type=type,
        status=status,
        has_match=has_match,
        page=page,
        page_size=page_size,
    )


@router.get("/my/items/{item_type}/{item_id}", response_model=MyItemDetailOut)
def get_my_item(
    item_type: str,
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MyItemDetailOut:
    if item_type not in (ItemType.lost.value, ItemType.found.value):
        raise ValidationError("未知的记录类型")
    return item_service.get_my_item_detail(
        db, user=user, item_type=item_type, item_id=item_id
    )


@router.patch("/my/items/{item_type}/{item_id}", response_model=MyItemOut)
def update_my_item(
    item_type: str,
    item_id: int,
    payload: ItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MyItemOut:
    if item_type not in (ItemType.lost.value, ItemType.found.value):
        raise ValidationError("未知的记录类型")
    item, ticket = item_service.update_item(
        db, user=user, item_type=item_type, item_id=item_id, payload=payload
    )
    out = item_service.serialize_my_item(item, item_type, ticket.ticket_no)
    db.commit()
    return out


@router.post("/my/items/{item_type}/{item_id}/withdraw", response_model=WithdrawOut)
def withdraw_item(
    item_type: str,
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WithdrawOut:
    result = item_service.withdraw(db, user=user, item_type=item_type, item_id=item_id)
    return WithdrawOut(**result)


@router.post("/my/items/{item_type}/{item_id}/resubmit")
def resubmit_item(
    item_type: str,
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    result = item_service.resubmit(db, user=user, item_type=item_type, item_id=item_id)
    db.commit()
    return result


@router.post("/my/items/{item_type}/{item_id}/delist-request")
def request_delist(
    item_type: str,
    item_id: int,
    payload: DelistApplyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ticket = review_service.apply_delist(
        db, user=user, item_type=item_type, item_id=item_id, reason=payload.reason
    )
    return {"ticket_no": ticket.ticket_no, "status": ticket.status}


@router.post("/uploads", status_code=201)
def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict:
    _require_user(user)
    object_key, mime_type, size_bytes, thumb_key = image_service.save_image(file)
    return {
        "object_key": object_key,
        "thumb_key": thumb_key,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "url": item_service.image_url(object_key),
        "thumb_url": f"/api/v1/images/{thumb_key}" if thumb_key else None,
    }