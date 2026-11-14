"""运营统计服务（仅管理员可见）。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.db.enums import ItemStatus, ReviewStatus
from app.db.models import ClaimRequest, FoundItem, LostItem, MatchRecord
from app.schemas.admin import StatisticsOut


def statistics(db: Session) -> StatisticsOut:
    lost_total = db.execute(select(func.count(LostItem.id))).scalar_one()
    found_total = db.execute(select(func.count(FoundItem.id))).scalar_one()

    active_lost = db.execute(
        select(func.count(LostItem.id)).where(
            LostItem.status == ItemStatus.active.value, LostItem.is_removed.is_(False)
        )
    ).scalar_one()
    active_found = db.execute(
        select(func.count(FoundItem.id)).where(
            FoundItem.status == ItemStatus.active.value, FoundItem.is_removed.is_(False)
        )
    ).scalar_one()

    match_requests = db.execute(
        select(func.count(func.distinct(MatchRecord.batch_id)))
    ).scalar_one()
    claim_requests = db.execute(select(func.count(ClaimRequest.id))).scalar_one()
    pending_claims = db.execute(
        select(func.count(ClaimRequest.id)).where(
            ClaimRequest.review_status == ReviewStatus.pending.value
        )
    ).scalar_one()

    resolved_lost = db.execute(
        select(func.count(LostItem.id)).where(LostItem.status == ItemStatus.resolved.value)
    ).scalar_one()
    resolved_found = db.execute(
        select(func.count(FoundItem.id)).where(FoundItem.status == ItemStatus.resolved.value)
    ).scalar_one()

    return StatisticsOut(
        total_records=lost_total + found_total,
        active_records=active_lost + active_found,
        match_requests=match_requests,
        claim_requests=claim_requests,
        completed_records=resolved_lost + resolved_found,
        period=f"全部时间（生成时待处理认领 {pending_claims} 条）",
        generated_at=utcnow(),
    )