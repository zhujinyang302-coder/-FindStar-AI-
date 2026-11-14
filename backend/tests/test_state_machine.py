"""状态机单元测试：合法与非法转换。"""

from __future__ import annotations

import pytest

from app.core.response import ConflictError
from app.db.enums import ItemStatus
from app.services.state_machine import assert_transition, can_transition


def test_legal_transitions():
    assert can_transition(ItemStatus.active.value, ItemStatus.claimed.value)
    assert can_transition(ItemStatus.active.value, ItemStatus.resolved.value)
    assert can_transition(ItemStatus.claimed.value, ItemStatus.resolved.value)
    assert can_transition(ItemStatus.resolved.value, ItemStatus.closed.value)


def test_same_state_is_allowed():
    assert can_transition(ItemStatus.active.value, ItemStatus.active.value)


def test_illegal_transition_raises():
    with pytest.raises(ConflictError):
        assert_transition(ItemStatus.closed.value, ItemStatus.active.value)


def test_closed_is_terminal():
    assert can_transition(ItemStatus.closed.value, ItemStatus.closed.value)
    assert not can_transition(ItemStatus.closed.value, ItemStatus.resolved.value)