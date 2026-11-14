"""匹配受理与四层执行编排。

顺序固定：硬约束 → 语义召回 → 后端评分 → 阈值/配额。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai.provider import get_provider
from app.core.config import settings
from app.core.logging import get_logger
from app.core.response import ConflictError, NotFoundError
from app.core.timeutil import utcnow
from app.db.enums import (
    BatchStatus,
    CandidateStatus,
    DisclosureLevel,
    ItemLifecycleStatus as S,
    ItemType,
    MatchDirection,
)
from app.db.models import MatchBatch, MatchRecord, User
from app.services import audit, disclosure_service, explain_service, notification_service
from app.services import rate_limit, recall_service, scoring, semantic_service
from app.services.item_service import _model, get_item, to_side
from app.services.visibility_policy import can_initiate_match

logger = get_logger(__name__)


def _direction(initiated_type: str) -> str:
    return (
        MatchDirection.lost_to_found.value
        if initiated_type == ItemType.lost.value
        else MatchDirection.found_to_lost.value
    )


def derive_idempotency_key(
    *, initiated_type: str, initiated_id: int, data_version: int, salt: str = ""
) -> str:
    raw = (
        f"{initiated_type}:{initiated_id}:{data_version}:"
        f"{settings.match_algorithm_version}:{settings.match_config_version}:{salt}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _new_batch_id() -> str:
    return f"b_{uuid.uuid4().hex[:24]}"


def _existing_batch(db: Session, idempotency_key: str) -> MatchBatch | None:
    return db.execute(
        select(MatchBatch).where(MatchBatch.idempotency_key == idempotency_key)
    ).scalars().first()


def _create_batch(
    db: Session,
    *,
    initiated_type: str,
    initiated_item: Any,
    initiator_id: int,
    idempotency_key: str,
) -> MatchBatch:
    batch = MatchBatch(
        batch_id=_new_batch_id(),
        idempotency_key=idempotency_key,
        initiated_item_type=initiated_type,
        initiated_item_id=initiated_item.id,
        initiator_id=initiator_id,
        direction=_direction(initiated_type),
        status=BatchStatus.processing.value,
        algorithm_version=settings.match_algorithm_version,
        config_version=settings.match_config_version,
        data_version=int(initiated_item.data_version or 1),
        threshold=settings.match_score_threshold,
        quota=settings.match_candidate_quota,
        weights_snapshot=scoring.weights_snapshot(),
        recall_channel="keyword",
        visible=True,
        created_at=utcnow(),
    )
    db.add(batch)
    db.flush()
    return batch


def accept_match(
    db: Session,
    *,
    user: User,
    lost_item_id: int | None,
    found_item_id: int | None,
) -> tuple[MatchBatch, bool]:
    if (lost_item_id is None) == (found_item_id is None):
        from app.core.response import ValidationError

        raise ValidationError("必须且只能提供一个 lost_item_id 或 found_item_id")
    if lost_item_id is not None:
        initiated_type, initiated_id = ItemType.lost.value, lost_item_id
    else:
        initiated_type, initiated_id = ItemType.found.value, int(found_item_id or 0)

    item = get_item(db, initiated_type, initiated_id)
    if item.user_id != user.id:
        raise NotFoundError("记录不存在")
    if not can_initiate_match(item.status) or item.is_removed or not item.info_sufficient:
        raise ConflictError("记录当前状态不允许匹配", code="MATCH_NOT_ALLOWED")

    key = derive_idempotency_key(
        initiated_type=initiated_type,
        initiated_id=initiated_id,
        data_version=int(item.data_version or 1),
    )
    existing = _existing_batch(db, key)
    if existing is not None:
        if existing.status == BatchStatus.processing.value:
            run_batch(db, existing)
            db.refresh(existing)
        return existing, True

    rate_limit.check_and_increment(
        db, subject_type="user", subject_id=user.id, action="match_request"
    )
    rate_limit.check_and_increment(
        db,
        subject_type="item",
        subject_id=item.id,
        action="match_request",
        limit=settings.match_item_daily_limit,
    )

    batch = _create_batch(
        db,
        initiated_type=initiated_type,
        initiated_item=item,
        initiator_id=user.id,
        idempotency_key=key,
    )
    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="match_requested",
        entity_type=f"{initiated_type}_item",
        entity_id=item.id,
        batch_id=batch.batch_id,
    )
    db.commit()
    db.refresh(batch)
    run_batch(db, batch)
    db.refresh(batch)
    return batch, False


def enqueue_auto_match(
    db: Session, *, item_type: str, item: Any, initiator_id: int
) -> MatchBatch | None:
    """审核通过后只写任务行，由调度器执行。"""
    if not item.info_sufficient:
        return None
    key = derive_idempotency_key(
        initiated_type=item_type,
        initiated_id=item.id,
        data_version=int(item.data_version or 1),
    )
    existing = _existing_batch(db, key)
    if existing is not None:
        return existing
    return _create_batch(
        db,
        initiated_type=item_type,
        initiated_item=item,
        initiator_id=initiator_id,
        idempotency_key=key,
    )


def run_batch(db: Session, batch: MatchBatch) -> MatchBatch:
    now = utcnow()
    locked = db.execute(
        update(MatchBatch)
        .where(
            MatchBatch.id == batch.id,
            MatchBatch.status == BatchStatus.processing.value,
            (MatchBatch.locked_until.is_(None)) | (MatchBatch.locked_until < now),
        )
        .values(locked_until=now + timedelta(seconds=60), attempts=MatchBatch.attempts + 1)
    )
    if not locked.rowcount:
        db.rollback()
        return batch

    try:
        _execute(db, batch)
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch failed", extra={"error_category": type(exc).__name__})
        db.rollback()
        batch = db.get(MatchBatch, batch.id)
        batch.status = BatchStatus.degraded_completed.value
        batch.degraded = True
        batch.degraded_reason = f"匹配执行失败：{type(exc).__name__}"
        batch.completed_at = utcnow()
        batch.expires_at = utcnow() + timedelta(days=settings.match_result_ttl_days)
        db.commit()
    return batch


def _execute(db: Session, batch: MatchBatch) -> None:
    item = get_item(db, batch.initiated_item_type, batch.initiated_item_id)
    provider = get_provider()

    recall = recall_service.build_candidate_pool(
        db,
        initiated_item=item,
        initiated_type=batch.initiated_item_type,
        initiator_id=batch.initiator_id,
        window_days=settings.match_time_window_days,
        pool_max=settings.match_candidate_pool_max,
    )
    semantic = semantic_service.semantic_recall(
        initiated_item=item,
        pool=recall.candidates,
        top_k=settings.match_recall_top_k,
        provider=provider,
    )

    initiated_side = to_side(item, batch.initiated_item_type)
    scored: list[scoring.ScoredCandidate] = []
    for candidate_type, candidate in semantic.candidates:
        candidate_side = to_side(candidate, candidate_type)
        result = scoring.score_candidate(
            initiated_side,
            candidate_side,
            window_days=settings.match_time_window_days,
        )
        scored.append(
            scoring.ScoredCandidate(
                item_type=candidate_type, item=candidate, result=result
            )
        )
    ranked = scoring.rank(scored, initiated_side)
    threshold = float(batch.threshold)
    quota = min(int(batch.quota), settings.match_candidate_quota, 5)
    selected = [entry for entry in ranked if float(entry.result.total) >= threshold][
        :quota
    ]

    now = utcnow()
    expires_at = now + timedelta(days=settings.match_result_ttl_days)
    any_explain_unavailable = False
    for entry in selected:
        candidate_type = entry.item_type
        candidate_side = to_side(entry.item, candidate_type)
        explanation = explain_service.explain_candidate(
            provider=provider,
            initiated_side=initiated_side,
            candidate_side=candidate_side,
            result=entry.result,
        )
        if explanation.get("explanation_status") != "ready":
            any_explain_unavailable = True
        public_id = disclosure_service.candidate_public_id(
            batch.batch_id, candidate_type, entry.item.id
        )
        if candidate_type == ItemType.found.value:
            lost_id, found_id = item.id, entry.item.id
        else:
            lost_id, found_id = entry.item.id, item.id
        record = MatchRecord(
            batch_id=batch.batch_id,
            batch_fk=batch.id,
            candidate_public_id=public_id,
            initiated_item_type=batch.initiated_item_type,
            lost_item_id=lost_id,
            found_item_id=found_id,
            candidate_item_type=candidate_type,
            candidate_item_id=entry.item.id,
            score=entry.result.total,
            score_breakdown=entry.result.breakdown,
            reason_json={
                "summary": explanation.get("summary", ""),
                "reasons": explanation.get("reasons", []),
                "provider": explanation.get("provider"),
                "degraded": explanation.get("degraded"),
            },
            differences_json=explanation.get("differences", []),
            algorithm_version=batch.algorithm_version,
            status="proposed",
            disclosure_level=DisclosureLevel.summary.value,
            candidate_status=CandidateStatus.valid.value,
            explanation_status=explanation.get("explanation_status", "ready"),
            expires_at=expires_at,
            initiated_by=batch.initiator_id,
            created_at=now,
        )
        db.add(record)

    batch.filter_stats = recall.filter_stats
    batch.recall_channel = semantic.channel
    batch.recall_truncated = recall.truncated
    batch.candidate_count = len(selected)
    batch.completed_at = now
    batch.expires_at = expires_at
    batch.degraded = bool(semantic.degraded or recall.truncated or any_explain_unavailable)
    if semantic.degraded:
        batch.degraded_reason = "文本向量不可用，已回退关键词召回"
    elif recall.truncated:
        batch.degraded_reason = "候选池超出上限，已截断"
    elif any_explain_unavailable:
        batch.degraded_reason = "部分候选解释不可用"

    if not selected:
        batch.status = BatchStatus.no_candidates.value
        event = "match_no_candidate"
    elif semantic.degraded:
        batch.status = BatchStatus.degraded_completed.value
        event = "match_degraded"
    else:
        batch.status = BatchStatus.completed.value
        event = "match_completed"

    notification_service.notify(
        db,
        user_id=batch.initiator_id,
        event_type=event,
        ref_type="match_batch",
        ref_id=batch.id,
    )
    audit.record_audit(
        db,
        actor_id=batch.initiator_id,
        action="match_completed" if selected else "match_no_candidates",
        entity_type="match_batch",
        entity_id=batch.id,
        batch_id=batch.batch_id,
        after_status=batch.status,
        details={
            "candidate_count": len(selected),
            "recall_channel": semantic.channel,
            "degraded": batch.degraded,
        },
    )
    db.commit()


def process_processing_batches(db: Session, *, limit: int = 5) -> int:
    batches = db.execute(
        select(MatchBatch)
        .where(MatchBatch.status == BatchStatus.processing.value)
        .order_by(MatchBatch.created_at.asc())
        .limit(limit)
    ).scalars().all()
    processed = 0
    for batch in batches:
        now = utcnow()
        if batch.locked_until is not None and batch.locked_until > now:
            continue
        run_batch(db, batch)
        processed += 1
    return processed


def rematch(db: Session, *, user: User, lost_item_id: int | None, found_item_id: int | None) -> tuple[MatchBatch, bool]:
    if lost_item_id is not None:
        initiated_type, initiated_id = ItemType.lost.value, lost_item_id
    else:
        initiated_type, initiated_id = ItemType.found.value, int(found_item_id or 0)
    item = get_item(db, initiated_type, initiated_id)
    if item.user_id != user.id:
        raise NotFoundError("记录不存在")
    if not can_initiate_match(item.status) or not item.info_sufficient:
        raise ConflictError("记录当前状态不允许重新匹配", code="MATCH_NOT_ALLOWED")

    old = db.execute(
        select(MatchBatch).where(
            MatchBatch.initiated_item_type == initiated_type,
            MatchBatch.initiated_item_id == initiated_id,
            MatchBatch.status.in_(
                [BatchStatus.completed.value, BatchStatus.degraded_completed.value]
            ),
        )
    ).scalars().all()
    for batch in old:
        batch.status = BatchStatus.archived.value

    key = derive_idempotency_key(
        initiated_type=initiated_type,
        initiated_id=initiated_id,
        data_version=int(item.data_version or 1),
        salt=uuid.uuid4().hex,
    )
    batch = _create_batch(
        db,
        initiated_type=initiated_type,
        initiated_item=item,
        initiator_id=user.id,
        idempotency_key=key,
    )
    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="match_requested",
        entity_type=f"{initiated_type}_item",
        entity_id=item.id,
        batch_id=batch.batch_id,
        details={"rematch": True},
    )
    db.commit()
    db.refresh(batch)
    run_batch(db, batch)
    db.refresh(batch)
    return batch, False