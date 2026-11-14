"""SQLAlchemy ORM 模型（V3 目标态）。

表：users、lost_items、found_items、item_images、match_records、
claim_requests（历史兼容）、audit_logs、review_tickets、notifications、
idempotency_keys、match_batches、contact_requests、disclosure_access_logs、
match_feedback、rate_limit_counters、security_events、item_semantic_index、
match_config_versions。

以 MySQL 为目标方言，同时兼容 SQLite（开发/演示）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.db.base import Base
from app.db.enums import (
    BatchStatus,
    CandidateStatus,
    ContactStatus,
    DisclosureLevel,
    DraftStatus,
    ItemStatus,
    MatchBatchKind,
    MatchStatus,
    ReviewStatus,
    ReviewTicketStatus,
    ThresholdSource,
    UserRole,
    UserStatus,
    VisibilityScope,
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=UserRole.user.value)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=UserStatus.active.value
    )
    migration_notice_seen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class LostItem(Base):
    __tablename__ = "lost_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    location_code: Mapped[str] = mapped_column(String(100), nullable=False, default="未知")
    location_text: Mapped[str] = mapped_column(String(200), nullable=False)
    lost_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    features: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ItemStatus.active.value, index=True
    )
    is_removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    latest_ticket_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delist_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delisted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    visibility_scope: Mapped[str] = mapped_column(
        String(24), nullable=False, default=VisibilityScope.owner_only.value
    )
    info_sufficient: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    images: Mapped[list["ItemImage"]] = relationship(
        "ItemImage",
        primaryjoin="and_(ItemImage.item_type=='lost', foreign(ItemImage.item_id)==LostItem.id)",
        viewonly=True,
        lazy="selectin",
    )


class FoundItem(Base):
    __tablename__ = "found_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    location_code: Mapped[str] = mapped_column(String(100), nullable=False, default="未知")
    location_text: Mapped[str] = mapped_column(String(200), nullable=False)
    found_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    features: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ItemStatus.active.value, index=True
    )
    is_removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    latest_ticket_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delist_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delisted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    visibility_scope: Mapped[str] = mapped_column(
        String(24), nullable=False, default=VisibilityScope.owner_only.value
    )
    info_sufficient: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    images: Mapped[list["ItemImage"]] = relationship(
        "ItemImage",
        primaryjoin="and_(ItemImage.item_type=='found', foreign(ItemImage.item_id)==FoundItem.id)",
        viewonly=True,
        lazy="selectin",
    )


class ItemImage(Base):
    __tablename__ = "item_images"
    __table_args__ = (Index("ix_item_images_type_id", "item_type", "item_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_type: Mapped[str] = mapped_column(String(8), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    thumb_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    watermark_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sensitive_masked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MatchDraft(Base):
    """未发布的匹配草稿；不进入记录表、候选池与正式统计。"""

    __tablename__ = "match_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    item_type: Mapped[str] = mapped_column(String(8), nullable=False, default="lost")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=DraftStatus.matching.value, index=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    location_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_text: Mapped[str] = mapped_column(String(200), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    info_sufficient: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    preview_batch_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    published_item_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    published_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    matching_notice_accepted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def user_id(self) -> int:
        """供召回链路按发起人排除同账号候选。"""
        return self.owner_id

    @property
    def lost_at(self) -> datetime | None:
        """供时间窗口与方向约束复用正式召回实现。"""
        return self.occurred_at

    @property
    def features(self):
        return None

    @property
    def is_removed(self) -> bool:
        return False


class MatchDraftImage(Base):
    __tablename__ = "match_draft_images"
    __table_args__ = (
        UniqueConstraint("draft_id", "object_key", name="uq_draft_image"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    thumb_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    watermark_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MatchPreviewCandidate(Base):
    """预览候选；不复用 match_records，避免伪造正式匹配关联。"""

    __tablename__ = "match_preview_candidates"
    __table_args__ = (
        UniqueConstraint(
            "candidate_public_id", name="uq_preview_candidate_public_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    batch_fk: Mapped[int | None] = mapped_column(
        ForeignKey("match_batches.id"), nullable=True, index=True
    )
    candidate_public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_item_type: Mapped[str] = mapped_column(
        String(8), nullable=False, default="found"
    )
    candidate_item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    differences_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    explanation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ready"
    )
    requires_offline_verification: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    low_similar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    disclosure_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DisclosureLevel.summary.value
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CandidateStatus.valid.value
    )
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    draft_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MatchBatch(Base):
    __tablename__ = "match_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    initiated_item_type: Mapped[str] = mapped_column(String(8), nullable=False)
    initiated_item_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    initiator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=BatchStatus.processing.value, index=True
    )
    algorithm_version: Mapped[str] = mapped_column(String(40), nullable=False)
    config_version: Mapped[str] = mapped_column(String(40), nullable=False)
    data_version: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    quota: Mapped[int] = mapped_column(Integer, nullable=False)
    weights_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recall_channel: Mapped[str] = mapped_column(String(16), nullable=False, default="keyword")
    recall_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    degraded_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filter_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    batch_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=MatchBatchKind.formal.value,
        server_default=MatchBatchKind.formal.value,
    )
    threshold_source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ThresholdSource.formal.value,
        server_default=ThresholdSource.formal.value,
    )
    draft_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MatchRecord(Base):
    """候选记录（沿用表名，承载候选与解释）。"""

    __tablename__ = "match_records"
    __table_args__ = (
        Index("ix_match_lost_found", "lost_item_id", "found_item_id", "score"),
        UniqueConstraint(
            "batch_id", "lost_item_id", "found_item_id", name="uq_match_batch_pair"
        ),
        UniqueConstraint("candidate_public_id", name="uq_match_candidate_public_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    batch_fk: Mapped[int | None] = mapped_column(
        ForeignKey("match_batches.id"), nullable=True, index=True
    )
    candidate_public_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    initiated_item_type: Mapped[str] = mapped_column(String(8), nullable=False)
    lost_item_id: Mapped[int] = mapped_column(
        ForeignKey("lost_items.id"), nullable=False, index=True
    )
    found_item_id: Mapped[int] = mapped_column(
        ForeignKey("found_items.id"), nullable=False, index=True
    )
    candidate_item_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    candidate_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    differences_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    algorithm_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=MatchStatus.proposed.value
    )
    disclosure_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DisclosureLevel.summary.value
    )
    candidate_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=CandidateStatus.valid.value
    )
    explanation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ready"
    )
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    initiated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ClaimRequest(Base):
    """历史认领表（V3 保留用于迁移；新流程走 contact_requests）。"""

    __tablename__ = "claim_requests"
    __table_args__ = (
        Index("ix_claim_claimant_target", "claimant_id", "lost_item_id", "found_item_id"),
        UniqueConstraint("active_lock_key", name="uq_claim_active_lock"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int | None] = mapped_column(
        ForeignKey("match_records.id"), nullable=True
    )
    lost_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("lost_items.id"), nullable=True
    )
    found_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("found_items.id"), nullable=True
    )
    claimant_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    target_item_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    target_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_lock_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    private_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReviewStatus.pending.value, index=True
    )
    confirmer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ContactRequest(Base):
    __tablename__ = "contact_requests"
    __table_args__ = (
        Index("ix_contact_applicant", "applicant_id", "created_at"),
        Index("ix_contact_target_owner", "target_owner_id", "status"),
        UniqueConstraint("active_lock_key", name="uq_contact_active_lock"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_type: Mapped[str] = mapped_column(String(24), nullable=False)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    candidate_public_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    candidate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_item_type: Mapped[str] = mapped_column(String(8), nullable=False)
    target_item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    private_verification: Mapped[str | None] = mapped_column(Text, nullable=True)
    handover_location_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    handover_window_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    handover_window_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    handover_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ContactStatus.pending.value, index=True
    )
    decider_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active_lock_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sensitive_category: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DisclosureAccessLog(Base):
    __tablename__ = "disclosure_access_logs"
    __table_args__ = (Index("ix_disclosure_batch", "batch_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    disclosure_level: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MatchFeedback(Base):
    __tablename__ = "match_feedback"
    __table_args__ = (
        UniqueConstraint(
            "candidate_public_id", "reporter_id", name="uq_feedback_candidate_reporter"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_public_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    candidate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class RateLimitCounter(Base):
    __tablename__ = "rate_limit_counters"
    __table_args__ = (
        UniqueConstraint(
            "subject_type", "subject_id", "action", "window_start",
            name="uq_rate_limit_subject_window",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    window_start: Mapped[str] = mapped_column(String(10), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    handled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ItemSemanticIndex(Base):
    __tablename__ = "item_semantic_index"
    __table_args__ = (
        UniqueConstraint(
            "item_type", "item_id", "model_version", name="uq_semantic_item_model"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_type: Mapped[str] = mapped_column(String(8), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class MatchConfigVersion(Base):
    __tablename__ = "match_config_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    quota: Mapped[int] = mapped_column(Integer, nullable=False)
    time_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recall_strategy: Mapped[str] = mapped_column(String(40), nullable=False, default="vector_first")
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ReviewTicket(Base):
    __tablename__ = "review_tickets"
    __table_args__ = (Index("ix_review_queue", "review_type", "status", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_no: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    review_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="owner_request")
    item_type: Mapped[str] = mapped_column(String(8), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    applicant_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReviewTicketStatus.pending.value, index=True
    )
    opinion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notification_user", "user_id", "is_read", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivery_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "scope", "key", name="uq_idempotency_user_scope_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    candidate_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    disclosure_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    before_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    after_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)