"""先匹配后发布：草稿生命周期服务。"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.listing_modes import AUDIT_ITEM_AUTO_APPROVED, is_match_first_publish
from app.core.response import BusinessError, ConflictError, GoneError, NotFoundError
from app.core.timeutil import utcnow
from app.db.enums import BatchStatus, DraftStatus, MatchBatchKind, ThresholdSource
from app.db.models import MatchBatch, MatchDraft, MatchDraftImage, MatchPreviewCandidate
from app.schemas.item import FoundItemCreate, LostItemCreate
from app.services import audit, listing_policy, preview_service
from app.services.item_service import _validate_image_keys  # noqa: PLC2701


def _draft_id() -> str:
    return f"d_{uuid.uuid4().hex}"


def _payload_key(user_id: int, payload: LostItemCreate, header_key: str | None) -> str:
    if header_key:
        return header_key
    raw = json.dumps(
        {"user": user_id, **payload.model_dump(mode="json")},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _find_by_key(db: Session, key: str) -> MatchDraft | None:
    return db.execute(
        select(MatchDraft).where(MatchDraft.idempotency_key == key)
    ).scalars().first()


def _recent_same_content(db: Session, draft: MatchDraft) -> MatchDraft | None:
    cutoff = utcnow() - timedelta(minutes=5)
    return db.execute(
        select(MatchDraft).where(
            MatchDraft.owner_id == draft.owner_id,
            MatchDraft.id != draft.id,
            MatchDraft.status.in_(
                [
                    DraftStatus.matching.value,
                    DraftStatus.previewed.value,
                    DraftStatus.abandoned.value,
                ]
            ),
            MatchDraft.created_at >= cutoff,
            MatchDraft.title == draft.title,
            MatchDraft.description == draft.description,
            MatchDraft.category == draft.category,
            MatchDraft.location_text == draft.location_text,
        )
    ).scalars().first()


def _expire_if_needed(db: Session, draft: MatchDraft) -> None:
    if draft.expires_at <= utcnow() and draft.status in {
        DraftStatus.matching.value,
        DraftStatus.previewed.value,
        DraftStatus.abandoned.value,
    }:
        draft.status = DraftStatus.expired.value
        preview_service.invalidate_preview(db, draft)
        audit.record_audit(
            db,
            actor_id=None,
            actor_role="system",
            action="draft_expired",
            entity_type="match_draft",
            entity_id=draft.id,
            after_status=DraftStatus.expired.value,
        )
        db.flush()
        raise GoneError("草稿已过期，请重新发布", code="DRAFT_EXPIRED")


def create_draft(
    db: Session,
    *,
    user: Any,
    payload: LostItemCreate,
    header_key: str | None,
) -> tuple[MatchDraft, bool]:
    if not is_match_first_publish():
        raise ConflictError(
            "当前为直接发布模式", code="PUBLISH_MODE_DIRECT"
        )
    if not payload.matching_notice_accepted:
        raise BusinessError(
            "首次上传需确认匹配告知", code="NOTICE_NOT_ACCEPTED", status_code=422
        )
    if not payload.info_sufficient:
        raise BusinessError(
            "请至少上传 1 张图片或填写不少于 20 字的描述",
            code="INSUFFICIENT_INFO",
            status_code=422,
        )
    image_keys = list(payload.image_keys or [])
    _validate_image_keys(db, image_keys)
    for key in image_keys:
        used = db.execute(
            select(MatchDraftImage.id).where(MatchDraftImage.object_key == key)
        ).scalar_one_or_none()
        if used is not None:
            raise BusinessError(
                "图片已被其他草稿引用", code="INVALID_IMAGE_KEY", status_code=422
            )

    risk = listing_policy.precheck(
        title=payload.title, description=payload.description
    )
    if risk.blocked:
        raise BusinessError(
            "内容包含不允许发布的信息",
            code="CONTENT_RISK_BLOCKED",
            status_code=422,
        )

    key = _payload_key(user.id, payload, header_key)
    existing = _find_by_key(db, key)
    if existing is not None:
        _expire_if_needed(db, existing)
        return existing, True

    now = utcnow()
    draft = MatchDraft(
        draft_id=_draft_id(),
        owner_id=user.id,
        item_type="lost",
        status=DraftStatus.matching.value,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        color=payload.color,
        brand=payload.brand,
        location_code=payload.location_code,
        location_text=payload.location_text,
        occurred_at=payload.occurred_at,
        info_sufficient=True,
        data_version=1,
        idempotency_key=key,
        matching_notice_accepted=True,
        expires_at=now + timedelta(days=settings.draft_ttl_days),
        created_at=now,
        updated_at=now,
    )
    db.add(draft)
    db.flush()

    for object_key in image_keys:
        from app.services.image_service import stat_image

        mime, size = stat_image(object_key)
        db.add(
            MatchDraftImage(
                draft_id=draft.draft_id,
                object_key=object_key,
                mime_type=mime,
                size_bytes=size,
                created_at=now,
            )
        )

    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="draft_created",
        entity_type="match_draft",
        entity_id=draft.id,
        after_status=draft.status,
    )

    batch = preview_service.accept_preview(db, draft)
    draft.status = (
        DraftStatus.previewed.value
        if batch.status
        not in {
            BatchStatus.processing.value,
            BatchStatus.invalidated.value,
            BatchStatus.expired.value,
        }
        else DraftStatus.matching.value
    )
    draft.updated_at = utcnow()
    db.flush()
    return draft, False


def get_draft(db: Session, *, user: Any, draft_id: str) -> MatchDraft:
    draft = db.execute(
        select(MatchDraft).where(MatchDraft.draft_id == draft_id)
    ).scalars().first()
    if draft is None or draft.owner_id != user.id:
        raise NotFoundError("草稿不存在")
    _expire_if_needed(db, draft)
    return draft


def list_my_drafts(db: Session, *, user: Any, limit: int = 50) -> list[MatchDraft]:
    draft_ids = [
        row.id
        for row in db.execute(
            select(MatchDraft)
            .where(
                MatchDraft.owner_id == user.id,
                MatchDraft.status.in_(
                    [
                        DraftStatus.matching.value,
                        DraftStatus.previewed.value,
                        DraftStatus.abandoned.value,
                    ]
                ),
                MatchDraft.expires_at > utcnow(),
            )
            .order_by(MatchDraft.created_at.desc())
            .limit(limit)
        ).scalars().all()
    ]
    return [
        db.execute(select(MatchDraft).where(MatchDraft.id == item)).scalars().one()
        for item in draft_ids
    ]


def abandon_draft(db: Session, *, user: Any, draft_id: str) -> MatchDraft:
    draft = get_draft(db, user=user, draft_id=draft_id)
    if draft.status == DraftStatus.published.value:
        raise ConflictError("已发布草稿不可放弃", code="DRAFT_STATE_CHANGED")
    if draft.status == DraftStatus.expired.value:
        raise GoneError("草稿已过期", code="DRAFT_EXPIRED")
    draft.status = DraftStatus.abandoned.value
    draft.updated_at = utcnow()
    preview_service.invalidate_preview(db, draft)
    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="draft_abandoned",
        entity_type="match_draft",
        entity_id=draft.id,
        after_status=draft.status,
    )
    db.flush()
    return draft


def _preview_candidates(db: Session, draft: MatchDraft):
    batch = db.execute(
        select(MatchBatch).where(MatchBatch.batch_id == draft.preview_batch_id)
    ).scalars().first()
    if batch is None:
        return None, []
    rows = db.execute(
        select(MatchPreviewCandidate)
        .where(
            MatchPreviewCandidate.batch_id == batch.batch_id,
            MatchPreviewCandidate.status == "valid",
        )
        .order_by(MatchPreviewCandidate.score.desc())
    ).scalars().all()
    return batch, rows


def publish_draft(db: Session, *, user: Any, draft_id: str) -> dict:
    draft = get_draft(db, user=user, draft_id=draft_id)
    if draft.status == DraftStatus.published.value and draft.published_item_id:
        item = db.get(
            __import__(
                "app.db.models", fromlist=["LostItem"]
            ).LostItem,
            draft.published_item_id,
        )
        return {
            "item_id": draft.published_item_id,
            "item_type": "lost",
            "status": item.status if item else "active",
            "review_ticket_no": None,
            "data_version": int(item.data_version or 1) if item else 1,
            "batch_id": None,
            "preview_reused": False,
            "publish_flow": "match_first",
        }
    if draft.status == DraftStatus.expired.value:
        raise GoneError("草稿已过期，请重新提交", code="DRAFT_EXPIRED")
    if draft.status not in {
        DraftStatus.matching.value,
        DraftStatus.previewed.value,
        DraftStatus.abandoned.value,
    }:
        raise ConflictError("草稿状态不允许发布", code="DRAFT_STATE_CHANGED")

    payload = LostItemCreate(
        title=draft.title,
        description=draft.description,
        category=draft.category,
        color=draft.color,
        brand=draft.brand,
        location_code=draft.location_code,
        location_text=draft.location_text,
        occurred_at=draft.occurred_at,
        image_keys=[
            row.object_key
            for row in db.execute(
                select(MatchDraftImage).where(
                    MatchDraftImage.draft_id == draft.draft_id
                )
            ).scalars().all()
        ],
        matching_notice_accepted=True,
    )

    has_formal = False

    from app.services import item_service

    item, ticket = item_service.create_item(
        db, user=user, item_type="lost", payload=payload
    )

    formal = db.execute(
        select(MatchBatch)
        .where(
            MatchBatch.initiated_item_type == "lost",
            MatchBatch.initiated_item_id == item.id,
        )
        .order_by(MatchBatch.id.desc())
    ).scalars().first()
    if formal is not None and not has_formal:
        formal.threshold = settings.match_preview_threshold
        formal.threshold_source = ThresholdSource.first_formal.value
        formal.draft_id = draft.draft_id

    draft.status = DraftStatus.published.value
    draft.published_item_type = "lost"
    draft.published_item_id = item.id
    draft.updated_at = utcnow()

    audit.record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action="draft_published",
        entity_type="match_draft",
        entity_id=draft.id,
        after_status=draft.status,
        details={
            "item_id": item.id,
            "publish_flow": "match_first",
            "ticket_no": ticket.ticket_no,
        },
    )
    db.flush()
    return {
        "item_id": item.id,
        "item_type": "lost",
        "status": item.status,
        "review_ticket_no": ticket.ticket_no,
        "data_version": int(item.data_version or 1),
        "batch_id": formal.batch_id if formal else None,
        "preview_reused": False,
        "publish_flow": "match_first",
    }