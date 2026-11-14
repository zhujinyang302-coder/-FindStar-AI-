from __future__ import annotations

from datetime import datetime

from app.services import disclosure_policy as policy


def test_phone_masked_not_blocked():
    text = policy.sanitize_disclosure_text("联系电话 13800138000，请尽快联系")
    assert "13800138000" not in text
    assert "***" in text


def test_email_and_student_no_masked():
    text = policy.sanitize_disclosure_text("邮箱 a@b.com 学号 A202301234")
    assert "a@b.com" not in text
    assert "A202301234" not in text


def test_excerpt_truncates_with_ellipsis():
    assert policy.excerpt("一二三四五六七八九十", 5) == "一二三四五…"
    assert policy.excerpt("短文本", 5) == "短文本"


def test_area_name_mapping_and_fallback():
    assert policy.area_name("LIB-3F") == "校园内"
    assert policy.area_name("图书馆三楼") == "图书馆区域"
    assert policy.area_name("未知") == "校园内"


def test_sensitive_category():
    assert policy.requires_offline_verification("证件卡类") is True
    assert policy.requires_offline_verification("电子产品") is False


def test_occurred_window():
    assert policy.occurred_window(datetime(2026, 11, 1, 9, 30)) == "09:00-12:00"
    assert policy.occurred_window(None) is None


def test_visible_features_limited():
    features = {"visible_features": ["a", "b", "c", "d", "e", "f"]}
    assert len(policy.visible_features(features)) == 5


def test_whitelist_rejects_forbidden():
    try:
        policy.ensure_whitelist({"owner_id": 1}, policy.SUMMARY_FIELDS)
        raise AssertionError("should reject")
    except ValueError:
        pass