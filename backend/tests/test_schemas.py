"""字段校验单元测试：类别枚举、时间边界、脚本输入防护。"""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.core.timeutil import utcnow
from app.schemas.item import FoundItemCreate, LostItemCreate


def _payload(**overrides):
    data = dict(
        title="黑色无线耳机",
        description="黑色无线耳机，可能落在教学楼",
        category="电子产品",
        location_text="教学楼二楼",
    )
    data.update(overrides)
    return data


def test_valid_payload_passes():
    item = LostItemCreate(**_payload())
    assert item.category == "电子产品"


def test_category_must_be_in_enum():
    with pytest.raises(ValidationError):
        LostItemCreate(**_payload(category="不存在的类别"))


def test_future_time_rejected():
    with pytest.raises(ValidationError):
        FoundItemCreate(**_payload(occurred_at=utcnow() + timedelta(days=1)))


def test_past_time_accepted():
    item = LostItemCreate(**_payload(occurred_at=utcnow() - timedelta(days=1)))
    assert item.occurred_at is not None


def test_script_input_rejected():
    with pytest.raises(ValidationError):
        LostItemCreate(**_payload(title="<script>alert(1)</script>"))


def test_too_many_images_rejected():
    with pytest.raises(ValidationError):
        LostItemCreate(**_payload(image_keys=["a", "b", "c", "d", "e", "f"]))