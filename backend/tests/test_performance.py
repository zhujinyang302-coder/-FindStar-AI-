from __future__ import annotations

import math
import time
from datetime import datetime

import pytest

from app.ai.matching import ItemSide, score_pair
from app.core.config import settings


def _side(index: int) -> ItemSide:
    return ItemSide(
        title=f"黑色双肩包 {index}",
        description="图书馆三楼自习区拾到黑色双肩包，包内有蓝色水杯和一本线性代数教材",
        category="钱包箱包",
        color="黑色",
        brand=None,
        location_code="LIB-3F",
        location_text="图书馆三楼",
        occurred_at=datetime(2026, 11, 1, 9, 0),
    )


@pytest.mark.slow
def test_candidate_pool_scoring_p95_within_budget():
    query = _side(0)
    pool = [_side(index) for index in range(settings.match_candidate_pool_max)]

    started = time.perf_counter()
    durations: list[float] = []
    for candidate in pool:
        tick = time.perf_counter()
        score_pair(query, candidate, window_days=settings.match_time_window_days)
        durations.append((time.perf_counter() - tick) * 1000)
    total_seconds = time.perf_counter() - started

    durations.sort()
    p95_index = max(0, math.ceil(0.95 * len(durations)) - 1)
    p95_seconds = durations[p95_index] / 1000
    assert p95_seconds <= settings.match_total_budget_seconds
    assert total_seconds <= settings.match_total_budget_seconds