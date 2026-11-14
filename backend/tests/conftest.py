"""pytest 共享配置：内存数据库、测试用户与鉴权头。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("BACKGROUND_JOBS_ENABLED", "false")
os.environ.setdefault("CACHE_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.enums import UserRole, UserStatus
from app.db.models import User
from app.db.session import get_db
from app.main import app

settings.background_jobs_enabled = False
settings.cache_enabled = False
settings.auto_approve_listing = False
settings.auto_match_on_approve = False


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.clear()


def make_user(
    db, *, email: str, role: str = UserRole.user.value, nickname: str | None = None
) -> User:
    user = User(
        nickname=nickname or email.split("@")[0],
        email=email,
        password_hash=hash_password("User@2026"),
        role=role,
        status=UserStatus.active.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auto_mode(monkeypatch):
    """显式切换到自动通过模式；用例结束后恢复人工模式基线。"""
    monkeypatch.setattr(settings, "auto_approve_listing", True)
    monkeypatch.setattr(settings, "auto_match_on_approve", True)
    return settings


@pytest.fixture()
def manual_mode(monkeypatch):
    monkeypatch.setattr(settings, "auto_approve_listing", False)
    return settings


@pytest.fixture()
def match_first_mode(monkeypatch):
    monkeypatch.setattr(settings, "match_first_publish_enabled", True)
    monkeypatch.setattr(settings, "auto_approve_listing", True)
    monkeypatch.setattr(settings, "auto_match_on_approve", True)
    return settings


@pytest.fixture()
def user(db_session) -> User:
    return make_user(db_session, email="alice@test.demo", nickname="失主")


@pytest.fixture()
def other_user(db_session) -> User:
    return make_user(db_session, email="bob@test.demo", nickname="拾获者")


@pytest.fixture()
def admin(db_session) -> User:
    return make_user(db_session, email="admin@test.demo", role=UserRole.admin.value, nickname="管理员")


def unwrap(response):
    payload = response.json()
    return payload.get("data", payload)


ITEM_PAYLOAD = {
    "title": "黑色双肩包",
    "description": "图书馆三楼自习区拾到，包内有蓝色水杯和一本线性代数教材",
    "category": "钱包箱包",
    "color": "黑色",
    "location_code": "LIB-3F",
    "location_text": "图书馆三楼自习区",
    "image_keys": [],
    "matching_notice_accepted": True,
}


def create_item(client, headers, payload=None, item_type: str = "found") -> dict:
    body = dict(ITEM_PAYLOAD)
    if payload:
        body.update(payload)
    response = client.post(f"/api/v1/{item_type}-items", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return unwrap(response)


def approve(client, admin_headers, ticket_no: str) -> dict:
    response = client.post(
        f"/api/v1/admin/review/tickets/{ticket_no}/decide",
        json={"decision": "approve", "opinion": "资料完整，同意上架"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    return unwrap(response)

# ---------- 服务层辅助（沙箱环境下避免真实 HTTP/套接字） ----------
def service_create_item(db, user, payload=None, item_type: str = "found"):
    from app.services import item_service

    body = dict(ITEM_PAYLOAD)
    if payload:
        body.update(payload)
    if item_type == "lost":
        from app.schemas.item import LostItemCreate

        schema = LostItemCreate(**body)
    else:
        from app.schemas.item import FoundItemCreate

        schema = FoundItemCreate(**body)
    return item_service.create_item(db, user=user, item_type=item_type, payload=schema)


def service_approve(db, admin, ticket) -> None:
    from app.services import review_service

    review_service.decide(
        db,
        admin=admin,
        ticket_no=ticket.ticket_no,
        decision="approve",
        opinion="资料完整，同意上架",
    )