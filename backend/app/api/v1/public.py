"""公开只读接口：仅返回聚合完成数。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.db.enums import ItemLifecycleStatus
from app.db.models import FoundItem, LostItem
from app.db.session import get_db
from app.schemas.public import PublicStatsOut
from app.services.visibility_policy import public_statistics_scope

router = APIRouter(prefix="/public", tags=["public"])

_ALLOWED = public_statistics_scope()


@router.get("/stats", response_model=PublicStatsOut)
def public_stats(db: Session = Depends(get_db)) -> PublicStatsOut:
    assert _ALLOWED == frozenset({"completed_total"})
    completed = {ItemLifecycleStatus.claimed.value, ItemLifecycleStatus.resolved.value}
    lost_total = db.execute(
        select(func.count(LostItem.id)).where(LostItem.status.in_(completed))
    ).scalar_one()
    found_total = db.execute(
        select(func.count(FoundItem.id)).where(FoundItem.status.in_(completed))
    ).scalar_one()
    return PublicStatsOut(
        completed_total=int(lost_total + found_total),
        generated_at=utcnow(),
    )