"""no_candidates 批次读取修复的回归用例。

不依赖 TestClient（沙箱 socketpair 受限），直接验证读取裁决与路由函数。
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.api.v1 import matches as matches_api
from app.core.batch_status import is_readable_terminal
from app.core.response import ConflictError, GoneError, NotFoundError
from app.core.timeutil import utcnow
from app.db.enums import BatchStatus
from app.db.models import (
    DisclosureAccessLog,
    FoundItem,
    LostItem,
    MatchBatch,
    MatchRecord,
    RateLimitCounter,
)
from app.schemas.match import FeedbackRequest

READABLE_STATUSES = {
    BatchStatus.completed.value,
    BatchStatus.degraded_completed.value,
    BatchStatus.no_candidates.value,
}

ALL_STATUSES = [
    BatchStatus.processing.value,
    BatchStatus.completed.value,
    BatchStatus.no_candidates.value,
    BatchStatus.degraded_completed.value,
    BatchStatus.invalidated.value,
    BatchStatus.expired.value,
    BatchStatus.archived.value,
]

_DEFAULT = object()


@pytest.fixture()
def lost_item(db_session, user) -> LostItem:
    item = LostItem(
        user_id=user.id,
        title="黑色双肩包",
        category="钱包箱包",
        location_text="图书馆三楼自习区",
        status="active",
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


@pytest.fixture()
def found_item(db_session, other_user) -> FoundItem:
    item = FoundItem(
        user_id=other_user.id,
        title="黑色双肩包",
        category="钱包箱包",
        location_text="图书馆三楼自习区",
        status="active",
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _batch(
    db,
    *,
    status: str,
    item: LostItem,
    user,
    expires_at=_DEFAULT,
    visible: bool = True,
    degraded: bool = False,
    candidate_count: int = 0,
) -> MatchBatch:
    now = utcnow()
    if expires_at is _DEFAULT:
        expires_at = now + timedelta(days=1)
    batch = MatchBatch(
        batch_id=f"b_{uuid4().hex}",
        idempotency_key=f"k_{uuid4().hex}",
        initiated_item_type="lost",
        initiated_item_id=item.id,
        initiator_id=user.id,
        direction="lost_to_found",
        status=status,
        algorithm_version="v3",
        config_version="v3",
        data_version=1,
        threshold=65.0,
        quota=3,
        degraded=degraded,
        degraded_reason="文本向量不可用，已回退关键词召回" if degraded else None,
        candidate_count=candidate_count,
        visible=visible,
        created_at=now,
        completed_at=None if status == BatchStatus.processing.value else now,
        expires_at=expires_at,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_readable_terminal_status_set(status):
    assert is_readable_terminal(status) is (status in READABLE_STATUSES)


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_assert_readable_seven_states(db_session, user, lost_item, status):
    batch = _batch(db_session, status=status, item=lost_item, user=user)
    if status in READABLE_STATUSES or status == BatchStatus.processing.value:
        matches_api._assert_readable(db_session, batch)
    else:
        with pytest.raises(GoneError):
            matches_api._assert_readable(db_session, batch)


def test_no_candidates_batch_out_fields(db_session, user, lost_item):
    batch = _batch(
        db_session,
        status=BatchStatus.no_candidates.value,
        item=lost_item,
        user=user,
        degraded=True,
    )
    out = matches_api._batch_out(batch)
    assert out.status == BatchStatus.no_candidates.value
    assert out.candidate_count == 0
    assert out.message == "暂无可靠候选"
    assert out.degraded is True
    assert out.degraded_reason == "文本向量不可用，已回退关键词召回"
    assert out.expires_at == batch.expires_at
    assert out.algorithm_version == "v3"


def test_no_candidates_invisible_still_404(db_session, user, lost_item):
    batch = _batch(
        db_session,
        status=BatchStatus.no_candidates.value,
        item=lost_item,
        user=user,
        visible=False,
    )
    with pytest.raises(NotFoundError):
        matches_api._assert_readable(db_session, batch)


def test_no_candidates_elapsed_expires(db_session, user, lost_item):
    batch = _batch(
        db_session,
        status=BatchStatus.no_candidates.value,
        item=lost_item,
        user=user,
        expires_at=utcnow() - timedelta(seconds=1),
    )
    with pytest.raises(GoneError):
        matches_api._assert_readable(db_session, batch)
    db_session.refresh(batch)
    assert batch.status == BatchStatus.expired.value


def test_no_candidates_missing_expires_at_expires(db_session, user, lost_item):
    batch = _batch(
        db_session,
        status=BatchStatus.no_candidates.value,
        item=lost_item,
        user=user,
        expires_at=None,
    )
    with pytest.raises(GoneError):
        matches_api._assert_readable(db_session, batch)
    db_session.refresh(batch)
    assert batch.status == BatchStatus.expired.value


def test_no_candidates_inactive_item_gone(db_session, user, lost_item):
    batch = _batch(
        db_session,
        status=BatchStatus.no_candidates.value,
        item=lost_item,
        user=user,
    )
    lost_item.status = "closed"
    db_session.commit()
    with pytest.raises(GoneError):
        matches_api._assert_readable(db_session, batch)


def test_candidates_list_empty_contract_without_side_effects(db_session, user, lost_item):
    batch = _batch(
        db_session,
        status=BatchStatus.no_candidates.value,
        item=lost_item,
        user=user,
    )
    before_rate = db_session.query(RateLimitCounter).count()
    before_logs = db_session.query(DisclosureAccessLog).count()

    out = matches_api.list_candidates(
        request=None,
        batch=batch,
        db=db_session,
        user=user,
        category=None,
        color=None,
        time_from=None,
        time_to=None,
        area_code=None,
        keyword=None,
    )

    assert out.batch_id == batch.batch_id
    assert out.candidates == []
    assert out.filtered_total == 0
    assert out.total == 0
    assert out.disclosure_level == "summary"
    assert out.sort_note
    assert out.disclaimer
    assert db_session.query(RateLimitCounter).count() == before_rate
    assert db_session.query(DisclosureAccessLog).count() == before_logs


def test_processing_candidates_still_409(db_session, user, lost_item):
    batch = _batch(
        db_session,
        status=BatchStatus.processing.value,
        item=lost_item,
        user=user,
    )
    with pytest.raises(ConflictError):
        matches_api.list_candidates(
            request=None,
            batch=batch,
            db=db_session,
            user=user,
            category=None,
            color=None,
            time_from=None,
            time_to=None,
            area_code=None,
            keyword=None,
        )


def test_completed_candidates_path_unchanged(db_session, user, lost_item):
    batch = _batch(
        db_session,
        status=BatchStatus.completed.value,
        item=lost_item,
        user=user,
        candidate_count=0,
    )
    matches_api._assert_readable(db_session, batch)
    assert is_readable_terminal(batch.status)


def _record(db, *, batch: MatchBatch, lost_item: LostItem, found_item: FoundItem, user):
    record = MatchRecord(
        batch_id=batch.batch_id,
        candidate_public_id=f"c_{uuid4().hex}",
        initiated_item_type="lost",
        lost_item_id=lost_item.id,
        found_item_id=found_item.id,
        candidate_item_type="found",
        candidate_item_id=found_item.id,
        score=80,
        score_breakdown={
            "text": {"score": 0.8, "weight": 0.35},
            "image": {"score": 0.0, "weight": 0.25, "available": False},
            "location": {"score": 1.0, "weight": 0.2},
            "time": {"score": 0.5, "weight": 0.15},
            "attribute": {"score": 0.6, "weight": 0.05},
        },
        reason_json={"reasons": ["同类目", "同地点"]},
        algorithm_version="v3",
        initiated_by=user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def test_candidate_detail_no_candidates_404(
    db_session, user, lost_item, found_item
):
    batch = _batch(
        db_session,
        status=BatchStatus.no_candidates.value,
        item=lost_item,
        user=user,
    )
    record = _record(
        db_session, batch=batch, lost_item=lost_item, found_item=found_item, user=user
    )
    with pytest.raises(NotFoundError):
        matches_api.candidate_detail(
            request=None,
            candidate_public_id=record.candidate_public_id,
            batch=batch,
            db=db_session,
            user=user,
        )


def test_candidate_explanation_no_candidates_404(
    db_session, user, lost_item, found_item
):
    batch = _batch(
        db_session,
        status=BatchStatus.no_candidates.value,
        item=lost_item,
        user=user,
    )
    record = _record(
        db_session, batch=batch, lost_item=lost_item, found_item=found_item, user=user
    )
    with pytest.raises(NotFoundError):
        matches_api.candidate_explanation(
            request=None,
            candidate_public_id=record.candidate_public_id,
            db=db_session,
            user=user,
        )


def test_candidate_feedback_no_candidates_404(
    db_session, user, lost_item, found_item
):
    batch = _batch(
        db_session,
        status=BatchStatus.no_candidates.value,
        item=lost_item,
        user=user,
    )
    record = _record(
        db_session, batch=batch, lost_item=lost_item, found_item=found_item, user=user
    )
    with pytest.raises(NotFoundError):
        matches_api.candidate_feedback(
            candidate_public_id=record.candidate_public_id,
            payload=FeedbackRequest(feedback_type="not_mine"),
            response=None,
            db=db_session,
            user=user,
        )