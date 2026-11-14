"""发布内容风控与确定性抽检。

分级：硬拦截 fail-closed、软风险放行并强制抽检、风控异常 fail-open。
本模块不判定违规、不修改记录状态，只产出预检结论与抽检标记。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.core.config import settings

_SALT = "findstar-listing-sample-v1"


@dataclass(frozen=True)
class RiskResult:
    blocked: bool = False
    soft: bool = False
    error: bool = False
    sampled: bool = False


def _contains(text: str, words: list[str]) -> bool:
    lowered = text.lower()
    return any(
        word.strip() and word.strip().lower() in lowered for word in words if word
    )


def precheck(*, title: str, description: str) -> RiskResult:
    if not settings.listing_risk_check_enabled:
        return RiskResult()
    try:
        text = f"{title}\n{description}"
        if _contains(text, settings.listing_risk_denylist):
            return RiskResult(blocked=True)
        if _contains(text, settings.listing_risk_soft_keywords):
            return RiskResult(soft=True, sampled=True)
    except Exception:  # noqa: BLE001
        return RiskResult(error=True, sampled=True)
    return RiskResult()


def deterministic_sample(item_type: str, item_id: int) -> bool:
    rate = settings.listing_sample_rate
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    digest = hashlib.sha256(f"{item_type}:{item_id}:{_SALT}".encode()).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return bucket < rate


def is_sampled(item_type: str, item_id: int, risk: RiskResult) -> bool:
    return bool(risk.sampled or deterministic_sample(item_type, item_id))