from __future__ import annotations

from app.db.models import User
from app.services import notification_service


def test_notification_text_is_sanitized(db_session, user):
    row = notification_service.notify(
        db_session,
        user_id=user.id,
        event_type="contact_received",
        body="请联系 13800138000 或 a@b.com",
    )
    db_session.commit()
    assert "13800138000" not in row.body
    assert "a@b.com" not in row.body
    assert "***" in row.body


def test_notification_templates_do_not_leak_candidate_content(db_session, user):
    row = notification_service.notify(
        db_session, user_id=user.id, event_type="match_completed"
    )
    db_session.commit()
    assert "候选" not in row.body.replace("已生成候选", "")
    assert row.title == "匹配完成"


def test_list_unread_and_mark_read(db_session, user):
    for _ in range(3):
        notification_service.notify(
            db_session, user_id=user.id, event_type="review_result"
        )
    db_session.commit()
    rows, total, unread = notification_service.list_notifications(
        db_session, user_id=user.id
    )
    assert total == 3
    assert unread == 3

    notification_service.mark_read(
        db_session, user_id=user.id, notification_id=rows[0].id
    )
    db_session.commit()
    assert notification_service.unread_count(db_session, user_id=user.id) == 2

    updated = notification_service.mark_all_read(db_session, user_id=user.id)
    db_session.commit()
    assert updated == 2
    assert notification_service.unread_count(db_session, user_id=user.id) == 0


def test_mark_read_isolated_by_user(db_session, user, other_user):
    row = notification_service.notify(
        db_session, user_id=user.id, event_type="review_result"
    )
    db_session.commit()
    assert (
        notification_service.mark_read(
            db_session, user_id=other_user.id, notification_id=row.id
        )
        is False
    )


def test_deliver_skips_disabled_user(db_session, user):
    notification_service.notify(
        db_session, user_id=user.id, event_type="review_result"
    )
    user.status = "disabled"
    db_session.commit()
    assert notification_service.deliver_pending(db_session) == 0
    _, _, _ = notification_service.list_notifications(db_session, user_id=user.id)