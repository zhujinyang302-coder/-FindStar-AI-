"""管理端记录管理接口（仅管理员）。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.response import ValidationError
from app.db.models import User
from app.db.session import get_db
from app.schemas.admin_records import (
    AdminDelistOut,
    AdminDelistRequest,
    AdminRecordDetailOut,
    AdminRecordListOut,
)
from app.services import admin_record_service

router = APIRouter(prefix="/admin/records", tags=["admin-records"])


@router.get("", response_model=AdminRecordListOut)
def list_records(
    type: str = Query(default="all", pattern="^(all|lost|found)$"),
    status: str = Query(default="all"),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    keyword: str | None = Query(default=None, max_length=50),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminRecordListOut:
    if status not in {
        "all",
        "pending_listing",
        "active",
        "listing_rejected",
        "delisting_review",
        "delisted",
        "claimed",
        "resolved",
        "closed",
    }:
        raise ValidationError("未知的记录状态")
    return admin_record_service.list_records(
        db,
        item_type=type,
        status=status,
        created_from=created_from,
        created_to=created_to,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


@router.get("/{item_type}/{item_id}", response_model=AdminRecordDetailOut)
def get_record(
    item_type: str,
    item_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminRecordDetailOut:
    result = admin_record_service.get_record(
        db, admin=admin, item_type=item_type, item_id=item_id
    )
    db.commit()
    return result


@router.post("/{item_type}/{item_id}/delist", response_model=AdminDelistOut)
def direct_delist(
    item_type: str,
    item_id: int,
    payload: AdminDelistRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminDelistOut:
    result = admin_record_service.direct_delist(
        db, admin=admin, item_type=item_type, item_id=item_id, reason=payload.reason
    )
    db.commit()
    return result