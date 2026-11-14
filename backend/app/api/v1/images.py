"""图片访问策略。

原图仅记录发布者与审核可读；缩略图仅在批次有效期内对发起人可读；其他一律 404。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_optional_user
from app.core.response import NotFoundError
from app.core.timeutil import utcnow
from app.db.enums import BatchStatus, UserRole
from app.db.models import ItemImage, MatchBatch, MatchRecord, User
from app.db.session import get_db
from app.services import image_service

router = APIRouter(tags=["images"])

_VALID_BATCH = {
    BatchStatus.completed.value,
    BatchStatus.degraded_completed.value,
}


@router.get("/images/{object_key}")
def get_image(
    object_key: str,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
) -> FileResponse:
    image = db.execute(
        select(ItemImage).where(
            or_(ItemImage.object_key == object_key, ItemImage.thumb_key == object_key)
        )
    ).scalars().first()
    if image is None:
        raise NotFoundError("图片不存在")
    is_original = image.object_key == object_key

    if viewer is None:
        raise NotFoundError("图片不存在")

    if is_original:
        if viewer.role == UserRole.admin.value or viewer.id == _owner_id(db, image):
            return _serve(object_key)
        raise NotFoundError("图片不存在")

    if viewer.role == UserRole.admin.value:
        raise NotFoundError("图片不存在")
    if not _batch_visible_to(
        db,
        viewer_id=viewer.id,
        item_type=image.item_type,
        item_id=image.item_id,
    ):
        raise NotFoundError("图片不存在")
    return _serve(object_key)


def _owner_id(db: Session, image: ItemImage) -> int | None:
    from app.services.item_service import _model

    item = db.get(_model(image.item_type), image.item_id)
    return item.user_id if item else None


def _batch_visible_to(
    db: Session, *, viewer_id: int, item_type: str, item_id: int
) -> bool:
    now = utcnow()
    batches = db.execute(
        select(MatchBatch).where(
            MatchBatch.initiator_id == viewer_id,
            MatchBatch.status.in_(_VALID_BATCH),
            MatchBatch.visible.is_(True),
            MatchBatch.expires_at.is_not(None),
            MatchBatch.expires_at > now,
        )
    ).scalars().all()
    if not batches:
        return False
    batch_ids = [batch.batch_id for batch in batches]
    record = db.execute(
        select(MatchRecord.id).where(
            MatchRecord.batch_id.in_(batch_ids),
            MatchRecord.candidate_item_type == item_type,
            MatchRecord.candidate_item_id == item_id,
            MatchRecord.candidate_status == "valid",
        )
    ).scalar_one_or_none()
    return record is not None


def _serve(object_key: str) -> FileResponse:
    path = image_service.resolve_path(object_key)
    if not path.is_file():
        raise NotFoundError("图片不存在")
    mime, _ = image_service.stat_image(object_key)
    return FileResponse(path, media_type=mime)