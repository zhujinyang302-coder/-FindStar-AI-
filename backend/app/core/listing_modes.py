"""发布模式唯一裁决出口。

模式只由部署配置决定：发布、修改、重提三个入口统一引用本模块，
不得从请求参数、请求头、用户属性或记录类型推断模式。
"""

from __future__ import annotations

from app.core.config import settings

AUTO = "auto"
MANUAL = "manual"

AUTO_APPROVAL_SOURCE = "auto_approval"
LEGACY_RELEASE_SOURCE = "legacy_release"
OWNER_REQUEST_SOURCE = "owner_request"
SYSTEM_RISK_SOURCE = "system_risk"
REPORT_SOURCE = "report"

AUTO_APPROVAL_OPINION = "系统自动通过"
LEGACY_RELEASE_OPINION = "存量迁移：系统自动通过"
LEGACY_REJECT_OPINION = "存量迁移：不满足自动上架条件"

AUDIT_ITEM_AUTO_APPROVED = "item_auto_approved"
NOTIFICATION_LISTING_AUTO_APPROVED = "listing_auto_approved"
LISTING_REVIEW_RETIRED_CODE = "LISTING_REVIEW_RETIRED"

PUBLISH_FLOW_MATCH_FIRST = "match_first"
PUBLISH_FLOW_PUBLISH_DIRECT = "publish_direct"


def current_review_mode() -> str:
    return AUTO if settings.auto_approve_listing else MANUAL


def is_auto_mode() -> bool:
    return bool(settings.auto_approve_listing)

def is_match_first_publish() -> bool:
    """发布形态只由部署配置裁决，禁止从请求推断。"""
    return bool(settings.match_first_publish_enabled)


def current_publish_flow() -> str:
    return (
        PUBLISH_FLOW_MATCH_FIRST
        if is_match_first_publish()
        else PUBLISH_FLOW_PUBLISH_DIRECT
    )