"""综合评分唯一出口（匹配第 3 层）。

分数只由 app/ai/matching.py 计算，本模块只负责调用与固定排序口径：
总分降序 → 时间接近度升序 → 地点接近度降序 → candidate_id 升序。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.ai.matching import BASE_WEIGHTS, ItemSide, ScoreResult, score_pair


@dataclass
class ScoredCandidate:
    item_type: str
    item: Any
    result: ScoreResult


def score_candidate(
    initiated_side: ItemSide, candidate_side: ItemSide, *, window_days: int
) -> ScoreResult:
    return score_pair(initiated_side, candidate_side, window_days=window_days)


def weights_snapshot() -> dict[str, float]:
    return dict(BASE_WEIGHTS)


def _time_gap(initiated: ItemSide, candidate: ItemSide) -> float:
    if initiated.occurred_at is None or candidate.occurred_at is None:
        return 9999.0
    return abs((initiated.occurred_at - candidate.occurred_at).total_seconds()) / 86400.0


def _location_score(result: ScoreResult) -> float:
    return float(result.breakdown.get("location", {}).get("score", 0.0))


def rank(scored: list[ScoredCandidate], initiated_side: ItemSide) -> list[ScoredCandidate]:
    return sorted(
        scored,
        key=lambda entry: (
            -float(entry.result.total),
            _time_gap(initiated_side, _side_of(entry)),
            -_location_score(entry.result),
            entry.item.id,
        ),
    )


def _side_of(entry: ScoredCandidate) -> ItemSide:
    from app.services.item_service import to_side

    return to_side(entry.item, entry.item_type)


def to_datetime(value: datetime | None) -> datetime | None:
    return value