"""披露策略纯函数：字段白名单、脱敏、模糊化与敏感类别。

白名单外字段在 DTO 结构上不存在，不依赖"置空"。
"""

from __future__ import annotations

import re

from app.db.enums import SENSITIVE_CATEGORIES

SUMMARY_FIELDS: frozenset[str] = frozenset(
    {
        "candidate_public_id",
        "item_type",
        "category",
        "color",
        "brand",
        "area_name",
        "occurred_on",
        "title_excerpt",
        "description_excerpt",
        "thumb_url",
        "score",
        "score_breakdown",
        "differences",
        "requires_offline_verification",
        "explanation_status",
        "reasons",
    }
)

VERIFIED_FIELDS: frozenset[str] = SUMMARY_FIELDS | frozenset(
    {"occurred_window", "location_text", "visible_features"}
)

HANDOVER_FIELDS: frozenset[str] = VERIFIED_FIELDS | frozenset(
    {"handover_location_code", "handover_window_start", "handover_window_end", "handover_note"}
)

# 任何层级都不允许出现的字段
FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "owner_id",
        "owner_nickname",
        "user_id",
        "applicant_id",
        "target_owner_id",
        "phone",
        "mobile",
        "email",
        "wechat",
        "qq",
        "student_no",
        "full_description",
        "original_url",
        "object_key",
    }
)

_PHONE = re.compile(r"1[3-9]\d{9}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_QQ_WECHAT = re.compile(r"(?:QQ|微信|wx|wechat|VX|vx)\s*[:：]?\s*[A-Za-z0-9_-]{5,}")
_ID_CARD = re.compile(r"\b\d{17}[\dXx]\b")
_STUDENT_NO = re.compile(r"\b[A-Za-z]\d{8,12}\b")

_AREA_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("图书馆", "图书馆区域"),
    ("宿舍", "宿舍区域"),
    ("食堂", "食堂区域"),
    ("教学楼", "教学楼区域"),
    ("操场", "运动场区域"),
    ("体育馆", "运动场区域"),
    ("实验室", "实验楼区域"),
    ("办公室", "办公楼区域"),
    ("校门", "校门区域"),
)


def sanitize_disclosure_text(text: str | None) -> str:
    if not text:
        return ""
    text = _PHONE.sub("***", text)
    text = _EMAIL.sub("***", text)
    text = _QQ_WECHAT.sub("***", text)
    text = _ID_CARD.sub("***", text)
    text = _STUDENT_NO.sub("***", text)
    return text.strip()


def excerpt(text: str | None, limit: int) -> str:
    cleaned = sanitize_disclosure_text(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "…"


def area_name(location_code: str | None) -> str:
    raw = (location_code or "").strip()
    for keyword, name in _AREA_KEYWORDS:
        if keyword in raw:
            return name
    return "校园内"


def requires_offline_verification(category: str | None) -> bool:
    return bool(category) and category in SENSITIVE_CATEGORIES


def occurred_window(occurred_at, *, hours: int = 3) -> str | None:
    if occurred_at is None:
        return None
    start = occurred_at.hour
    end = min(23, start + hours)
    return f"{start:02d}:00-{end:02d}:00"


def visible_features(features: dict | None, *, limit: int = 5) -> list[str]:
    if not features:
        return []
    values = features.get("visible_features")
    if not isinstance(values, list):
        return []
    return [sanitize_disclosure_text(str(value)) for value in values][:limit]


def ensure_whitelist(payload: dict, allowed: frozenset[str]) -> dict:
    for key in payload:
        if key in FORBIDDEN_FIELDS or key not in allowed:
            raise ValueError(f"披露字段越界：{key}")
    return payload