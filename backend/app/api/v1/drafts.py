"""先匹配后发布：草稿、预览与确认发布接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.listing_modes import is_match_first_publish
from app.core.response import ConflictError, GoneError, NotFoundError, RateLimitError
from app.core.timeutil import utcnow
from app.db.enums import (
    BatchStatus,
    DraftStatus,
    RateLimitAction,
    SENSITIVE_CATEGORIES,
    UserRole,
)
from app.db.models import (
    FoundItem,
    ItemImage,
    MatchBatch,
    MatchDraft,
    MatchDraftImage,
    MatchPreviewCandidate,
    User,
)
from app.db.session import get_db
from app.schemas.draft import (
    AbandonOut,
    DraftCandidateOut,
    DraftCreatedOut,
    DraftDetailOut,
    DraftImageOut,
    DraftListItem,
    DraftListOut,
    DraftPreviewOut,
    PublishModeOut,
    PublishOut,
)
from app.schemas.item import LostItemCreate
from app.services import draft_service, rate_limit

router = APIRouter(tags=["drafts"])


def _require_user(user: User) -> User:
    if user.role == UserRole.admin.value:
        raise NotFoundError("草稿不存在")
    return user


def _image_url(key: str | None) -> str | None:
    return f"/api/v1/images/{key}" if key else None


def _candidate_out(
    db: Session, row: MatchPreviewCandidate, threshold: float, source: str
) -> DraftCandidateOut:
    item = db.get(FoundItem, row.candidate_item_id)
    if item is None:
        raise NotFoundError("候选不存在")
    image = db.execute(
        select(ItemImage)
        .where(
            ItemImage.item_type == "found",
            ItemImage.item_id == item.id,
        )
        .order_by(ItemImage.id.asc())
    ).scalars().first()
    from app.services import disclosure_policy

    description = disclosure_policy.sanitize_disclosure_text(item.description or "")
    reasons = list((row.reason_json or {}).get("reasons") or [])
    return DraftCandidateOut(
        candidate_public_id=row.candidate_public_id,
        item_type="found",
        category=item.category,
        color=item.color,
        brand=item.brand,
        area_name=item.location_text or "校园内",
        occurred_on=item.found_at.date().isoformat() if item.found_at else None,
        title_excerpt=(item.title or "")[:20],
        description_excerpt=description[:60],
        thumb_url=_image_url((image.thumb_key if image else None) or (image.object_key if image else None)),
        score=float(row.score),
        score_breakdown=row.score_breakdown or {},
        differences=list(row.differences_json or []),
        requires_offline_verification=bool(
            row.requires_offline_verification or item.category in SENSITIVE_CATEGORIES
        ),
        explanation_status=row.explanation_status,
        reasons=reasons,
        low_similar=bool(row.low_similar),
        threshold=threshold,
        threshold_source=source,
    )


def _preview_out(db: Session, draft: MatchDraft) -> DraftPreviewOut:
    batch = (
        db.execute(
            select(MatchBatch).where(MatchBatch.batch_id == draft.preview_batch_id)
        ).scalars().first()
        if draft.preview_batch_id
        else None
    )
    if batch is None:
        return DraftPreviewOut(
            draft_id=draft.draft_id,
            status=DraftStatus.matching.value,
            candidate_count=0,
            threshold=settings.match_preview_threshold,
            threshold_source="preview",
        )
    if batch.status in {
        BatchStatus.invalidated.value,
        BatchStatus.expired.value,
    }:
        raise GoneError("预览已失效，请重新提交", code="DRAFT_PREVIEW_GONE")
    if batch.status == BatchStatus.processing.value:
        return DraftPreviewOut(
            draft_id=draft.draft_id,
            batch_id=batch.batch_id,
            status=batch.status,
            candidate_count=0,
            threshold=float(batch.threshold),
            threshold_source=batch.threshold_source,
            expires_at=batch.expires_at,
        )
    rows = db.execute(
        select(MatchPreviewCandidate)
        .where(
            MatchPreviewCandidate.batch_id == batch.batch_id,
            MatchPreviewCandidate.status == "valid",
        )
        .order_by(MatchPreviewCandidate.score.desc())
    ).scalars().all()
    candidates = [
        _candidate_out(db, row, float(batch.threshold), batch.threshold_source)
        for row in rows
    ]
    return DraftPreviewOut(
        draft_id=draft.draft_id,
        batch_id=batch.batch_id,
        status=batch.status,
        candidate_count=len(candidates),
        degraded=batch.degraded,
        degraded_reason=batch.degraded_reason,
        threshold=float(batch.threshold),
        threshold_source=batch.threshold_source,
        candidates=candidates,
        expires_at=batch.expires_at,
    )


@router.get("/config/publish-mode", response_model=PublishModeOut)
def publish_mode() -> PublishModeOut:
    return PublishModeOut(
        publish_mode="match_first" if is_match_first_publish() else "direct"
    )


@router.post("/lost-item-drafts", response_model=DraftCreatedOut, status_code=201)
def create_draft(
    payload: LostItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DraftCreatedOut:
    _require_user(user)
    try:
        rate_limit.check_and_increment(
            db,
            subject_type="user",
            subject_id=user.id,
            action=RateLimitAction.item_create.value,
        )
    except RateLimitError:
        raise
    except Exception:  # noqa: BLE001
        db.rollback()
    draft, replay = draft_service.create_draft(
        db, user=user, payload=payload, header_key=idempotency_key
    )
    db.commit()
    db.refresh(draft)
    return DraftCreatedOut(
        draft_id=draft.draft_id,
        status=draft.status,
        preview_batch_id=draft.preview_batch_id,
        expires_at=draft.expires_at,
        created_at=draft.created_at,
        idempotent_replay=replay,
    )


@router.get("/lost-item-drafts/{draft_id}", response_model=DraftDetailOut)
def get_draft(
    draft_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DraftDetailOut:
    _require_user(user)
    draft = draft_service.get_draft(db, user=user, draft_id=draft_id)
    db.commit()
    images = db.execute(
        select(MatchDraftImage).where(MatchDraftImage.draft_id == draft.draft_id)
    ).scalars().all()
    batch = (
        db.execute(
            select(MatchBatch).where(MatchBatch.batch_id == draft.preview_batch_id)
        ).scalars().first()
        if draft.preview_batch_id
        else None
    )
    return DraftDetailOut(
        draft_id=draft.draft_id,
        title=draft.title,
        description=draft.description,
        category=draft.category,
        color=draft.color,
        brand=draft.brand,
        location_code=draft.location_code,
        location_text=draft.location_text,
        occurred_at=draft.occurred_at,
        status=draft.status,
        expires_at=draft.expires_at,
        created_at=draft.created_at,
        preview_batch_id=draft.preview_batch_id,
        candidate_count=int(batch.candidate_count) if batch else 0,
        can_publish=draft.status
        in {
            DraftStatus.matching.value,
            DraftStatus.previewed.value,
            DraftStatus.abandoned.value,
        },
        images=[
            DraftImageOut(
                object_key=row.object_key,
                url=_image_url(row.object_key) or "",
                mime_type=row.mime_type,
                size_bytes=row.size_bytes,
            )
            for row in images
        ],
    )


@router.get("/lost-item-drafts/{draft_id}/preview", response_model=DraftPreviewOut)
def get_preview(
    draft_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DraftPreviewOut:
    _require_user(user)
    draft = draft_service.get_draft(db, user=user, draft_id=draft_id)
    out = _preview_out(db, draft)
    db.commit()
    return out


@router.post("/lost-item-drafts/{draft_id}/publish", response_model=PublishOut)
def publish_draft(
    draft_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PublishOut:
    _require_user(user)
    if not is_match_first_publish():
        raise ConflictError("当前为直接发布模式", code="PUBLISH_MODE_DIRECT")
    result = draft_service.publish_draft(db, user=user, draft_id=draft_id)
    db.commit()
    return PublishOut(**result)


@router.post("/lost-item-drafts/{draft_id}/abandon", response_model=AbandonOut)
def abandon_draft(
    draft_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AbandonOut:
    _require_user(user)
    draft = draft_service.abandon_draft(db, user=user, draft_id=draft_id)
    db.commit()
    return AbandonOut(draft_id=draft.draft_id, status=draft.status)


@router.get("/my/drafts", response_model=DraftListOut)
def list_my_drafts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DraftListOut:
    _require_user(user)
    drafts = draft_service.list_my_drafts(db, user=user, limit=50)
    start = (page - 1) * page_size
    items = []
    for draft in drafts[start : start + page_size]:
        batch = (
            db.execute(
                select(MatchBatch).where(MatchBatch.batch_id == draft.preview_batch_id)
            ).scalars().first()
            if draft.preview_batch_id
            else None
        )
        items.append(
            DraftListItem(
                draft_id=draft.draft_id,
                title=draft.title,
                status=draft.status,
                created_at=draft.created_at,
                expires_at=draft.expires_at,
                remaining_seconds=max(
                    0, int((draft.expires_at - utcnow()).total_seconds())
                ),
                candidate_count=int(batch.candidate_count) if batch else 0,
                can_publish=draft.status
                in {
                    DraftStatus.matching.value,
                    DraftStatus.previewed.value,
                    DraftStatus.abandoned.value,
                },
            )
        )
    return DraftListOut(items=items, total=len(drafts))