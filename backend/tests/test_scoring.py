from __future__ import annotations

from datetime import datetime, timedelta

from app.ai.matching import ItemSide
from app.services.scoring import rank, score_candidate, weights_snapshot


def _side(**overrides) -> ItemSide:
    base = dict(
        title="黑色双肩包",
        description="图书馆三楼自习区拾到，包内有蓝色水杯",
        category="钱包箱包",
        color="黑色",
        brand=None,
        location_code="LIB-3F",
        location_text="图书馆三楼",
        occurred_at=datetime(2026, 11, 1, 9, 0),
        features=None,
    )
    base.update(overrides)
    return ItemSide(**base)


def test_scoring_repeatable():
    a = _side()
    b = _side(title="黑色背包", location_code="LIB-2F")
    first = score_candidate(a, b, window_days=30)
    second = score_candidate(a, b, window_days=30)
    assert first.total == second.total
    assert first.breakdown == second.breakdown


def test_unavailable_image_weight_renormalized():
    result = score_candidate(_side(), _side(), window_days=30)
    assert result.breakdown["image"]["available"] is False
    total_weight = sum(part["weight"] for part in result.breakdown.values())
    assert abs(total_weight - 1.0) < 0.001
    assert result.breakdown["image"]["weight"] == 0.0


def test_weights_snapshot_is_baseline():
    assert weights_snapshot() == {
        "text": 0.35,
        "image": 0.25,
        "location": 0.20,
        "time": 0.15,
        "attribute": 0.05,
    }


def test_rank_prefers_higher_score():
    a = _side()
    high = score_candidate(a, _side(), window_days=30)
    low = score_candidate(
        a,
        _side(category="电子产品", color="红色", location_code="DORM-1", title="红色雨伞"),
        window_days=30,
    )
    from app.services.scoring import ScoredCandidate, rank

    class _Item:
        id = 99
        title = "黑色双肩包"
        description = "图书馆三楼自习区拾到，包内有蓝色水杯"
        category = "钱包箱包"
        color = "黑色"
        brand = None
        location_code = "LIB-3F"
        location_text = "图书馆三楼"
        occurred_at = datetime(2026, 11, 1, 9, 0)
        lost_at = occurred_at
        found_at = occurred_at
        features = None

    ranked = rank(
        [
            ScoredCandidate(item_type="found", item=_Item(), result=low),
            ScoredCandidate(item_type="found", item=_Item(), result=high),
        ],
        a,
    )
    assert ranked[0].result.total >= ranked[1].result.total


def test_time_proximity_breaks_tie():
    a = _side()
    near = score_candidate(a, _side(), window_days=30)
    far = score_candidate(
        a, _side(occurred_at=a.occurred_at - timedelta(days=20)), window_days=30
    )
    assert near.total >= far.total