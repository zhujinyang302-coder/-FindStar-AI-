"""匹配质量评估与配置版本治理。"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.response import ValidationError
from app.core.timeutil import utcnow
from app.db.models import (
    ContactRequest,
    MatchBatch,
    MatchConfigVersion,
    MatchFeedback,
    MatchRecord,
    User,
)
from app.db.enums import BatchStatus, ContactStatus
from app.schemas.admin import (
    MatchConfigCreateRequest,
    MatchConfigVersionListOut,
    MatchConfigVersionOut,
    QualityMetricsOut,
)

_INVALID_CACHE: dict[str, object] = {}


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return round(ordered[index], 2)


def metrics(
    db: Session,
    *,
    period_from: datetime | None = None,
    period_to: datetime | None = None,
    direction: str | None = None,
) -> QualityMetricsOut:
    end = period_to or utcnow()
    start = period_from or (end - timedelta(days=7))
    stmt = select(MatchBatch).where(
        MatchBatch.created_at >= start, MatchBatch.created_at <= end
    )
    if direction:
        stmt = stmt.where(MatchBatch.direction == direction)
    batches = db.execute(stmt).scalars().all()

    total = len(batches)
    no_candidate = len(
        [b for b in batches if b.status == BatchStatus.no_candidates.value]
    )
    degraded = len([b for b in batches if b.degraded])
    durations = [
        (b.completed_at - b.created_at).total_seconds() * 1000
        for b in batches
        if b.completed_at and b.created_at
    ]

    batch_ids = [b.batch_id for b in batches]
    candidate_count = 0
    confirmed_count = 0
    if batch_ids:
        candidate_count = int(
            db.execute(
                select(func.count(MatchRecord.id)).where(
                    MatchRecord.batch_id.in_(batch_ids)
                )
            ).scalar_one()
        )
        confirmed_count = int(
            db.execute(
                select(func.count(ContactRequest.id)).where(
                    ContactRequest.batch_id.in_(batch_ids),
                    ContactRequest.status == ContactStatus.confirmed.value,
                )
            ).scalar_one()
        )
    feedback_count = 0
    if batch_ids:
        feedback_count = int(
            db.execute(
                select(func.count(MatchFeedback.id)).where(
                    MatchFeedback.created_at >= start,
                    MatchFeedback.created_at <= end,
                )
            ).scalar_one()
        )

    return QualityMetricsOut(
        match_requests=total,
        no_candidate_rate=_ratio(no_candidate, total),
        top3_hit_rate=_ratio(confirmed_count, max(1, total)),
        user_false_positive_rate=_ratio(feedback_count, max(1, candidate_count)),
        degraded_rate=_ratio(degraded, total),
        candidate_p95_ms=_p95(durations),
        period_label=f"{start.date().isoformat()} ~ {end.date().isoformat()}",
        generated_at=utcnow(),
    )


def list_config_versions(db: Session) -> MatchConfigVersionListOut:
    rows = db.execute(
        select(MatchConfigVersion).order_by(MatchConfigVersion.created_at.desc())
    ).scalars().all()
    return MatchConfigVersionListOut(
        items=[
            MatchConfigVersionOut(
                version=row.version,
                threshold=float(row.threshold),
                quota=int(row.quota),
                time_window_days=int(row.time_window_days),
                weights=row.weights,
                recall_strategy=row.recall_strategy,
                changed_by=row.changed_by,
                reason=row.reason,
                active=row.active,
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


def create_config_version(
    db: Session, *, admin: User, payload: MatchConfigCreateRequest
) -> MatchConfigVersionOut:
    if payload.quota > 5:
        raise ValidationError("配额不得超过 5")
    if not 0.0 <= payload.threshold <= 100.0:
        raise ValidationError("阈值必须位于 [0, 100]")
    if not payload.reason or len(payload.reason.strip()) < 5:
        raise ValidationError("配置调整必须附不少于 5 字的理由")

    db.execute(MatchConfigVersion.__table__.update().values(active=False))
    version = f"cfg-{utcnow().strftime('%Y%m%d%H%M%S')}"
    row = MatchConfigVersion(
        version=version,
        threshold=payload.threshold,
        quota=payload.quota,
        time_window_days=payload.time_window_days,
        weights=payload.weights.model_dump() if payload.weights else None,
        recall_strategy="vector_first",
        changed_by=admin.id,
        reason=payload.reason,
        active=True,
        created_at=utcnow(),
    )
    db.add(row)

    from app.services import audit

    audit.record_audit(
        db,
        actor_id=admin.id,
        actor_role=admin.role,
        action="match_config_changed",
        entity_type="match_config_version",
        entity_id=0,
        reason=payload.reason,
        details={"version": version, "threshold": payload.threshold, "quota": payload.quota},
    )
    db.commit()
    db.refresh(row)
    return MatchConfigVersionOut(
        version=row.version,
        threshold=float(row.threshold),
        quota=int(row.quota),
        time_window_days=int(row.time_window_days),
        weights=row.weights,
        recall_strategy=row.recall_strategy,
        changed_by=row.changed_by,
        reason=row.reason,
        active=row.active,
        created_at=row.created_at,
    )


def feedback_metrics(db: Session) -> dict:
    rows = db.execute(
        select(
            MatchFeedback.feedback_type,
            func.count(MatchFeedback.id),
        ).group_by(MatchFeedback.feedback_type)
    ).all()
    return {"by_type": {row[0]: int(row[1]) for row in rows}}