"""先匹配后发布：预览批次受理与执行。

预览批次写入 match_batches（batch_kind='preview'），候选写入
match_preview_candidates，不写 match_records、不发通知。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.matching import ItemSide
from app.ai.provider import get_provider
from app.core.config import settings
from app.core.timeutil import utcnow
from app.db.enums import (
    BatchStatus,
    CandidateStatus,
    DisclosureLevel,
    MatchBatchKind,
    SENSITIVE_CATEGORIES,
    ThresholdSource,
)
from app.db.models import MatchBatch, MatchDraft, MatchPreviewCandidate
from app.services import (
    disclosure_service,
    explain_service,
    recall_service,
    scoring,
    semantic_service,
)
from app.services.match_orchestrator import derive_idempotency_key


def _new_batch_id() -> str:
    import uuid

    return f"b_{uuid.uuid4().hex[:24]}"


def _side(draft: MatchDraft) -> ItemSide:
    return ItemSide(
        title=draft.title,
        description=draft.description,
        category=draft.category,
        color=draft.color,
        brand=draft.brand,
        location_code=draft.location_code,
        location_text=draft.location_text,
        occurred_at=draft.occurred_at,
        features=None,
    )


def accept_preview(db: Session, draft: MatchDraft) -> MatchBatch:
    key = derive_idempotency_key(
        initiated_type="draft",
        initiated_id=draft.id,
        data_version=int(draft.data_version or 1),
        salt="preview",
    )
    existing = db.execute(
        select(MatchBatch).where(MatchBatch.idempotency_key == key)
    ).scalars().first()
    if existing is not None:
        return existing

    batch = MatchBatch(
        batch_id=_new_batch_id(),
        idempotency_key=key,
        initiated_item_type="draft",
        initiated_item_id=draft.id,
        initiator_id=draft.owner_id,
        direction="lost_to_found",
        status=BatchStatus.processing.value,
        algorithm_version=settings.match_algorithm_version,
        config_version=settings.match_config_version,
        data_version=int(draft.data_version or 1),
        threshold=settings.match_preview_threshold,
        quota=settings.match_candidate_quota,
        weights_snapshot=scoring.weights_snapshot(),
        recall_channel="keyword",
        visible=True,
        batch_kind=MatchBatchKind.preview.value,
        threshold_source=ThresholdSource.preview.value,
        draft_id=draft.draft_id,
        created_at=utcnow(),
    )
    db.add(batch)
    db.flush()
    draft.preview_batch_id = batch.batch_id
    run_preview(db, draft, batch)
    return batch


def run_preview(db: Session, draft: MatchDraft, batch: MatchBatch) -> MatchBatch:
    initiated_side = _side(draft)
    provider = get_provider()
    recall = recall_service.build_candidate_pool(
        db,
        initiated_item=draft,
        initiated_type="lost",
        initiator_id=draft.owner_id,
        window_days=settings.match_time_window_days,
        pool_max=settings.match_candidate_pool_max,
    )
    semantic = semantic_service.semantic_recall(
        initiated_item=draft,
        pool=recall.candidates,
        top_k=settings.match_recall_top_k,
        provider=provider,
    )

    scored: list[scoring.ScoredCandidate] = []
    for candidate_type, candidate in semantic.candidates:
        from app.services.item_service import to_side

        result = scoring.score_candidate(
            initiated_side,
            to_side(candidate, candidate_type),
            window_days=settings.match_time_window_days,
        )
        scored.append(
            scoring.ScoredCandidate(item_type=candidate_type, item=candidate, result=result)
        )
    ranked = scoring.rank(scored, initiated_side)
    threshold = float(batch.threshold)
    quota = min(int(batch.quota), settings.match_candidate_quota, 5)
    selected = [
        entry for entry in ranked if float(entry.result.total) >= threshold
    ][:quota]

    now = utcnow()
    expires_at = now + timedelta(days=settings.match_result_ttl_days)
    any_explain_unavailable = False
    for entry in selected:
        candidate_type = entry.item_type
        explanation = explain_service.explain_candidate(
            provider=provider,
            initiated_side=initiated_side,
            candidate_side=to_side(entry.item, candidate_type),
            result=entry.result,
        )
        if explanation.get("explanation_status") != "ready":
            any_explain_unavailable = True
        db.add(
            MatchPreviewCandidate(
                batch_id=batch.batch_id,
                batch_fk=batch.id,
                candidate_public_id=disclosure_service.candidate_public_id(
                    batch.batch_id, candidate_type, entry.item.id
                ),
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
                explanation_status=explanation.get("explanation_status", "ready"),
                requires_offline_verification=entry.item.category
                in SENSITIVE_CATEGORIES,
                low_similar=threshold
                <= float(entry.result.total)
                < settings.match_score_threshold,
                disclosure_level=DisclosureLevel.summary.value,
                status=CandidateStatus.valid.value,
                expires_at=expires_at,
                draft_id=draft.draft_id,
                created_at=now,
            )
        )

    batch.filter_stats = recall.filter_stats
    batch.recall_channel = semantic.channel
    batch.recall_truncated = recall.truncated
    batch.candidate_count = len(selected)
    batch.completed_at = now
    batch.expires_at = expires_at
    batch.degraded = bool(
        semantic.degraded or recall.truncated or any_explain_unavailable
    )
    if semantic.degraded:
        batch.degraded_reason = "文本向量不可用，已回退关键词召回"
    elif recall.truncated:
        batch.degraded_reason = "候选池超出上限，已截断"
    elif any_explain_unavailable:
        batch.degraded_reason = "部分候选解释不可用"

    if not selected:
        batch.status = BatchStatus.no_candidates.value
    elif semantic.degraded:
        batch.status = BatchStatus.degraded_completed.value
    else:
        batch.status = BatchStatus.completed.value
    db.flush()
    return batch


def invalidate_preview(db: Session, draft: MatchDraft) -> int:
    batches = db.execute(
        select(MatchBatch).where(
            MatchBatch.initiated_item_type == "draft",
            MatchBatch.initiated_item_id == draft.id,
            MatchBatch.batch_kind == MatchBatchKind.preview.value,
            MatchBatch.status.in_(
                [
                    BatchStatus.processing.value,
                    BatchStatus.completed.value,
                    BatchStatus.no_candidates.value,
                    BatchStatus.degraded_completed.value,
                ]
            ),
        )
    ).scalars().all()
    for batch in batches:
        batch.status = BatchStatus.invalidated.value
    if batches:
        db.execute(
            select(MatchPreviewCandidate).where(
                MatchPreviewCandidate.batch_id.in_([b.batch_id for b in batches])
            )
        )
        for row in db.execute(
            select(MatchPreviewCandidate).where(
                MatchPreviewCandidate.batch_id.in_([b.batch_id for b in batches])
            )
        ).scalars().all():
            row.status = CandidateStatus.invalidated.value
    return len(batches)