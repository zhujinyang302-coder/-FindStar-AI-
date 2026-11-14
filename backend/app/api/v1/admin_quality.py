"""管理端匹配质量与配置版本接口（仅聚合口径，不含候选明细）。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.models import User
from app.db.session import get_db
from app.schemas.admin import (
    MatchConfigCreateRequest,
    MatchConfigVersionListOut,
    MatchConfigVersionOut,
    QualityMetricsOut,
)
from app.services import quality_service

router = APIRouter(prefix="/admin/quality", tags=["admin-quality"])


@router.get("/metrics", response_model=QualityMetricsOut)
def metrics(
    period_from: datetime | None = Query(default=None, alias="from"),
    period_to: datetime | None = Query(default=None, alias="to"),
    direction: str | None = Query(default=None, pattern="^(lost_to_found|found_to_lost)$"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> QualityMetricsOut:
    return quality_service.metrics(
        db, period_from=period_from, period_to=period_to, direction=direction
    )


@router.get("/config-versions", response_model=MatchConfigVersionListOut)
def list_config_versions(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> MatchConfigVersionListOut:
    return quality_service.list_config_versions(db)


@router.post("/config-versions", response_model=MatchConfigVersionOut)
def create_config_version(
    payload: MatchConfigCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> MatchConfigVersionOut:
    return quality_service.create_config_version(db, admin=admin, payload=payload)