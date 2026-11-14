"""匹配解释生成（独立失败域）。

单候选解释失败只把该候选 explanation_status 置为 unavailable，保留分数；
模型输出必须经候选 ID 白名单与 schema 校验。
"""

from __future__ import annotations

from typing import Any

from app.ai.matching import ScoreResult
from app.ai.provider import AIUnavailableError, AIProvider
from app.core.logging import get_logger

logger = get_logger(__name__)


def explain_candidate(
    *,
    provider: AIProvider,
    initiated_side: Any,
    candidate_side: Any,
    result: ScoreResult,
) -> dict:
    context = {
        "score": result.total,
        "breakdown": result.breakdown,
        "computed_reasons": result.reasons,
        "differences": result.differences,
        "self_category": initiated_side.category,
        "candidate_category": candidate_side.category,
        "self_color": initiated_side.color,
        "candidate_color": candidate_side.color,
        "self_location": initiated_side.location_code,
        "candidate_location": candidate_side.location_code,
    }
    try:
        explanation = provider.explain_match(context=context)
        reasons = [str(x) for x in explanation.get("reasons", [])][:10] or result.reasons
        return {
            "summary": str(explanation.get("summary", ""))[:500],
            "reasons": reasons,
            "differences": result.differences,
            "explanation_status": "ready",
            "provider": provider.name,
            "degraded": provider.degraded,
        }
    except AIUnavailableError:
        logger.warning("explain unavailable", extra={"error_category": "AI_EXPLAIN_FAILED"})
        return {
            "summary": "解释生成不可用，已保留后端计算的分数与规则化理由。",
            "reasons": result.reasons,
            "differences": result.differences,
            "explanation_status": "unavailable",
            "provider": provider.name,
            "degraded": True,
        }
    except Exception:  # noqa: BLE001
        logger.warning("explain failed", extra={"error_category": "AI_EXPLAIN_FAILED"})
        return {
            "summary": "解释生成失败，已保留后端计算的分数与规则化理由。",
            "reasons": result.reasons,
            "differences": result.differences,
            "explanation_status": "unavailable",
            "provider": provider.name,
            "degraded": True,
        }