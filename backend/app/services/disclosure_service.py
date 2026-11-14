"""候选披露服务：不可推测标识、三级披露组装与访问留痕。"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.db.enums import ContactStatus, DisclosureLevel, ItemType
from app.db.models import ContactRequest, DisclosureAccessLog, MatchRecord
from app.schemas.match import (
    CandidateHandoverOut,
    CandidateSummaryOut,
    CandidateVerifiedOut,
    DifferenceItem,
    ScoreBreakdown,
    ScorePart,
)
from app.services import disclosure_policy as policy
from app.services.item_service import _model, _TIME_FIELD, to_side
from app.services.thumbnail_service import thumb_url


def candidate_public_id(
    batch_id: str, candidate_type: str, candidate_id: int
) -> str:
    raw = f"{batch_id}|{candidate_type}:{candidate_id}".encode("utf-8")
    digest = hmac.new(
        settings.app_secret_key.encode("utf-8"), raw, hashlib.sha256
    ).hexdigest()
    return f"c_{digest[:32]}"


def resolve_candidate(
    db: Session, *, batch_id: str, public_id: str
) -> tuple[MatchRecord, Any, str]:
    record = db.execute(
        select(MatchRecord).where(
            MatchRecord.batch_id == batch_id,
            MatchRecord.candidate_public_id == public_id,
        )
    ).scalars().first()
    if record is None:
        from app.core.response import NotFoundError

        raise NotFoundError("候选不存在")
    candidate_type = record.candidate_item_type or (
        ItemType.found.value
        if record.initiated_item_type == ItemType.lost.value
        else ItemType.lost.value
    )
    candidate_id = record.candidate_item_id or (
        record.found_item_id
        if candidate_type == ItemType.found.value
        else record.lost_item_id
    )
    item = db.get(_model(candidate_type), candidate_id)
    if item is None:
        from app.core.response import NotFoundError

        raise NotFoundError("候选不存在")
    return record, item, candidate_type


def find_by_public_id(db: Session, public_id: str) -> MatchRecord | None:
    return db.execute(
        select(MatchRecord).where(MatchRecord.candidate_public_id == public_id)
    ).scalars().first()


def _breakdown(raw: dict) -> ScoreBreakdown:
    return ScoreBreakdown(
        text=ScorePart(**raw["text"]),
        image=ScorePart(**raw["image"]),
        location=ScorePart(**raw["location"]),
        time=ScorePart(**raw["time"]),
        attribute=ScorePart(**raw["attribute"]),
    )


def _differences(record: MatchRecord) -> list[DifferenceItem]:
    raw = record.differences_json or (record.reason_json or {}).get("differences") or []
    items: list[DifferenceItem] = []
    for entry in raw:
        try:
            items.append(DifferenceItem(**entry))
        except Exception:  # noqa: BLE001
            continue
    return items


def _occurred(item: Any, item_type: str) -> datetime | None:
    return getattr(item, _TIME_FIELD[item_type])


def build_summary(
    db: Session, record: MatchRecord, item: Any, item_type: str
) -> CandidateSummaryOut:
    images = getattr(item, "images", []) or []
    thumb = thumb_url(images[0].thumb_key) if images else None
    occurred = _occurred(item, item_type)
    reasons = [str(x) for x in (record.reason_json or {}).get("reasons", [])][:10]
    return CandidateSummaryOut(
        candidate_public_id=record.candidate_public_id or "",
        item_type=item_type,
        category=item.category,
        color=item.color,
        brand=item.brand,
        area_name=policy.area_name(item.location_code),
        occurred_on=occurred.date().isoformat() if occurred else None,
        title_excerpt=policy.excerpt(item.title, 20),
        description_excerpt=policy.excerpt(item.description, 60),
        thumb_url=thumb,
        score=float(record.score),
        score_breakdown=_breakdown(record.score_breakdown),
        differences=_differences(record),
        requires_offline_verification=policy.requires_offline_verification(item.category),
        explanation_status=record.explanation_status,
        reasons=reasons,
    )


def build_verified(
    db: Session, record: MatchRecord, item: Any, item_type: str
) -> CandidateVerifiedOut:
    summary = build_summary(db, record, item, item_type)
    occurred = _occurred(item, item_type)
    return CandidateVerifiedOut(
        **summary.model_dump(),
        occurred_window=policy.occurred_window(occurred),
        location_text=item.location_text,
        visible_features=policy.visible_features(item.features),
    )


def build_handover(
    db: Session, record: MatchRecord, item: Any, item_type: str, contact: ContactRequest
) -> CandidateHandoverOut:
    verified = build_verified(db, record, item, item_type)
    return CandidateHandoverOut(
        **verified.model_dump(),
        handover_location_code=contact.handover_location_code,
        handover_window_start=contact.handover_window_start,
        handover_window_end=contact.handover_window_end,
        handover_note=contact.handover_note,
    )


def contact_for(db: Session, *, applicant_id: int, record: MatchRecord) -> ContactRequest | None:
    return db.execute(
        select(ContactRequest)
        .where(
            ContactRequest.applicant_id == applicant_id,
            ContactRequest.candidate_public_id == record.candidate_public_id,
        )
        .order_by(ContactRequest.created_at.desc())
    ).scalars().first()


def resolve_level(db: Session, *, applicant_id: int, record: MatchRecord) -> DisclosureLevel:
    contact = contact_for(db, applicant_id=applicant_id, record=record)
    if contact is None:
        return DisclosureLevel.summary
    if contact.status == ContactStatus.confirmed.value:
        return DisclosureLevel.handover
    if contact.status in {ContactStatus.pending.value, ContactStatus.rejected.value}:
        return DisclosureLevel.verified if contact.status == ContactStatus.pending.value else DisclosureLevel.summary
    return DisclosureLevel.summary


def log_access(
    db: Session,
    *,
    actor_id: int,
    batch_id: str,
    candidate_public_id: str,
    action: str,
    disclosure_level: str,
    request_id: str,
) -> None:
    db.add(
        DisclosureAccessLog(
            actor_id=actor_id,
            batch_id=batch_id,
            candidate_public_id=candidate_public_id,
            action=action,
            disclosure_level=disclosure_level,
            request_id=request_id,
            created_at=utcnow(),
        )
    )