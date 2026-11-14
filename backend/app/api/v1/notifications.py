"""站内通知接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.cache import get_cache
from app.core.response import NotFoundError
from app.db.models import User
from app.db.session import get_db
from app.schemas.notification import NotificationListOut, NotificationOut, UnreadCountOut
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListOut)
def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationListOut:
    rows, total, unread = notification_service.list_notifications(
        db, user_id=user.id, page=page, page_size=page_size
    )
    return NotificationListOut(
        items=[NotificationOut(**notification_service.notification_payload(row)) for row in rows],
        total=total,
        unread_count=unread,
    )


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UnreadCountOut:
    cache = get_cache()
    key = f"findstar:notify:unread:{user.id}"
    cached = cache.get_json(key)
    if cached is not None:
        return UnreadCountOut(unread_count=int(cached))
    count = notification_service.unread_count(db, user_id=user.id)
    cache.set_json(key, count, ttl=30)
    return UnreadCountOut(unread_count=count)


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if not notification_service.mark_read(
        db, user_id=user.id, notification_id=notification_id
    ):
        raise NotFoundError("通知不存在")
    db.commit()
    get_cache().delete(f"findstar:notify:unread:{user.id}")
    return {"id": notification_id, "is_read": True}


@router.post("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    count = notification_service.mark_all_read(db, user_id=user.id)
    db.commit()
    get_cache().delete(f"findstar:notify:unread:{user.id}")
    return {"updated": count}