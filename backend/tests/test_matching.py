"""匹配评分算法单元测试。

覆盖：边界值、正常值、类别冲突惩罚、地点/时间未知的中性分、评分可重复性。
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai.matching import ItemSide, score_pair  # noqa: E402
from app.core.timeutil import utcnow  # noqa: E402


def _side(**overrides) -> ItemSide:
    base = dict(
        title="黑色无线耳机",
        description="黑色无线耳机，可能落在教学楼",
        category="电子产品",
        color="黑色",
        brand=None,
        location_code="教学楼",
        location_text="教学楼二楼",
        occurred_at=utcnow() - timedelta(days=1),
        features=None,
    )
    base.update(overrides)
    return ItemSide(**base)


def test_same_item_scores_high():
    result = score_pair(_side(), _side())
    assert result.total >= 70
    assert result.category_conflict is False
    assert result.breakdown["text"]["score"] > 0.5


def test_category_conflict_penalized():
    good = score_pair(_side(), _side())
    conflict = score_pair(
        _side(),
        _side(category="雨具", color="蓝色", title="蓝色长柄雨伞", description="蓝色长柄雨伞"),
    )
    assert conflict.category_conflict is True
    assert conflict.total < good.total
    assert conflict.breakdown["attribute"]["score"] <= 0.2


def test_unknown_location_is_neutral():
    result = score_pair(_side(location_code="未知"), _side(location_code="未知"))
    assert result.breakdown["location"]["score"] == 0.5


def test_unknown_time_is_neutral():
    result = score_pair(_side(occurred_at=None), _side(occurred_at=None))
    assert result.breakdown["time"]["score"] == 0.5


def test_image_unavailable_flag_and_weight_renormalized():
    result = score_pair(_side(), _side())
    image_part = result.breakdown["image"]
    assert image_part["available"] is False
    # 视觉项不可用时，有效权重之和仍为 1（重新归一化；权重按 4 位小数展示）
    total_weight = sum(part["weight"] for part in result.breakdown.values())
    assert abs(total_weight - 1.0) < 1e-3


def test_scoring_is_repeatable():
    first = score_pair(_side(), _side())
    second = score_pair(_side(), _side())
    assert first.total == second.total
    assert first.breakdown == second.breakdown


def test_brand_unknown_does_not_penalize():
    result = score_pair(_side(brand=None), _side(brand=None))
    assert result.breakdown["attribute"]["score"] >= 0.5


def test_time_decay_beyond_window():
    recent = score_pair(_side(), _side())
    far = score_pair(_side(occurred_at=utcnow() - timedelta(days=90)), _side())
    assert far.breakdown["time"]["score"] < recent.breakdown["time"]["score"]