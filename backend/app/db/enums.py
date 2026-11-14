"""领域枚举（受控取值集合）。"""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    user = "user"
    admin = "admin"


class UserStatus(str, Enum):
    active = "active"
    disabled = "disabled"


class ItemType(str, Enum):
    lost = "lost"
    found = "found"


class ItemStatus(str, Enum):
    """物品生命周期状态。"""

    active = "active"
    claimed = "claimed"
    resolved = "resolved"
    closed = "closed"
    rejected = "rejected"


class ReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class MatchStatus(str, Enum):
    proposed = "proposed"
    confirmed = "confirmed"
    dismissed = "dismissed"


class ItemLifecycleStatus(str, Enum):
    """记录八态（V3 目标态）。"""

    pending_listing = "pending_listing"
    active = "active"
    listing_rejected = "listing_rejected"
    delisting_review = "delisting_review"
    delisted = "delisted"
    claimed = "claimed"
    resolved = "resolved"
    closed = "closed"


class MatchDirection(str, Enum):
    lost_to_found = "lost_to_found"
    found_to_lost = "found_to_lost"


class BatchStatus(str, Enum):
    processing = "processing"
    completed = "completed"
    no_candidates = "no_candidates"
    degraded_completed = "degraded_completed"
    invalidated = "invalidated"
    expired = "expired"
    archived = "archived"


class CandidateStatus(str, Enum):
    valid = "valid"
    invalidated = "invalidated"
    feedback_reported = "feedback_reported"
    confirmed = "confirmed"


class DisclosureLevel(str, Enum):
    summary = "summary"
    verified = "verified"
    handover = "handover"


class ContactType(str, Enum):
    claim = "claim"
    return_clue = "return_clue"


class ContactStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"
    closed = "closed"


class FeedbackType(str, Enum):
    not_mine = "not_mine"
    not_target = "not_target"
    inaccurate = "inaccurate"
    suspected_impersonation = "suspected_impersonation"


class RateLimitAction(str, Enum):
    match_request = "match_request"
    view_candidate = "view_candidate"
    view_summary = "view_summary"
    contact_submit = "contact_submit"
    view_batch = "view_batch"
    item_create = "item_create"


class NotificationType(str, Enum):
    match_completed = "match_completed"
    match_no_candidate = "match_no_candidate"
    match_degraded = "match_degraded"
    candidate_expiring = "candidate_expiring"
    candidate_expired = "candidate_expired"
    contact_received = "contact_received"
    contact_confirmed = "contact_confirmed"
    contact_rejected = "contact_rejected"
    contact_cooldown = "contact_cooldown"
    review_result = "review_result"
    listing_auto_approved = "listing_auto_approved"
    draft_expiring = "draft_expiring"
    admin_delisted = "admin_delisted"


class NotificationDelivery(str, Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"


class ReviewType(str, Enum):
    listing = "listing"
    delisting = "delisting"


class ReviewTicketStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class DelistSource(str, Enum):
    owner_request = "owner_request"
    report = "report"
    system_risk = "system_risk"
    admin_direct = "admin_direct"


class DisclosureAccessAction(str, Enum):
    view_summary = "view_summary"
    expand_reason = "expand_reason"
    submit_request = "submit_request"
    view_handover = "view_handover"


class VisibilityScope(str, Enum):
    owner_only = "owner_only"
    match_disclosure = "match_disclosure"


class DraftStatus(str, Enum):
    matching = "matching"
    previewed = "previewed"
    published = "published"
    abandoned = "abandoned"
    expired = "expired"


class MatchBatchKind(str, Enum):
    preview = "preview"
    formal = "formal"


class ThresholdSource(str, Enum):
    preview = "preview"
    first_formal = "first_formal"
    formal = "formal"


class AuditAction(str, Enum):
    draft_created = "draft_created"
    draft_published = "draft_published"
    draft_abandoned = "draft_abandoned"
    draft_expired = "draft_expired"
    preview_viewed = "preview_viewed"
    admin_record_viewed = "admin_record_viewed"
    admin_direct_delist = "admin_direct_delist"
    admin_match_denied = "admin_match_denied"


# 敏感类别：确认交接前必须线下核验
SENSITIVE_CATEGORIES: tuple[str, ...] = ("证件卡类", "钥匙")


# 受控类别枚举（AI 归一化与用户选择都必须落在其内）
ITEM_CATEGORIES: tuple[str, ...] = (
    "电子产品",
    "数码配件",
    "证件卡类",
    "钥匙",
    "钱包箱包",
    "衣物",
    "书籍文具",
    "水杯餐具",
    "雨具",
    "运动器材",
    "首饰配饰",
    "其他",
    "未知",
)

UNKNOWN = "未知"