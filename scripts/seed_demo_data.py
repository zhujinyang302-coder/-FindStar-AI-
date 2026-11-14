"""演示数据脚本（可重复执行，具备重复执行保护）。

用法：
    python scripts/seed_demo_data.py

说明：
- 使用虚构数据，不含真实个人信息。
- 演示管理员凭据来自环境变量 DEMO_ADMIN_EMAIL / DEMO_ADMIN_PASSWORD；
  未配置时在开发环境回退为固定演示账号并打印提示（禁止用于生产）。
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.timeutil import utcnow  # noqa: E402
from app.db.enums import ItemStatus, UserRole, UserStatus  # noqa: E402
from app.db.models import FoundItem, LostItem, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


def _get_or_create_user(db, *, nickname: str, email: str, password: str, role: str) -> User:
    user = db.execute(select(User).where(User.email == email)).scalars().first()
    if user:
        return user
    user = User(
        nickname=nickname,
        email=email,
        password_hash=hash_password(password),
        role=role,
        status=UserStatus.active.value,
    )
    db.add(user)
    db.flush()
    return user


def _create_lost(db, user_id: int, **kwargs) -> LostItem:
    title = kwargs["title"]
    exists = db.execute(
        select(LostItem).where(LostItem.title == title, LostItem.user_id == user_id)
    ).scalars().first()
    if exists:
        return exists
    item = LostItem(user_id=user_id, status=ItemStatus.active.value, is_removed=False, **kwargs)
    db.add(item)
    return item


def _create_found(db, user_id: int, **kwargs) -> FoundItem:
    title = kwargs["title"]
    exists = db.execute(
        select(FoundItem).where(FoundItem.title == title, FoundItem.user_id == user_id)
    ).scalars().first()
    if exists:
        return exists
    item = FoundItem(user_id=user_id, status=ItemStatus.active.value, is_removed=False, **kwargs)
    db.add(item)
    return item


def main() -> None:
    admin_email = settings.demo_admin_email or "admin@findstar.demo"
    admin_password = settings.demo_admin_password or "DemoAdmin@2026"
    if not settings.demo_admin_email:
        print("[seed] 未配置 DEMO_ADMIN_EMAIL，使用开发演示账号：", admin_email)

    db = SessionLocal()
    try:
        admin = _get_or_create_user(
            db, nickname="系统管理员", email=admin_email, password=admin_password, role=UserRole.admin.value
        )
        alice = _get_or_create_user(
            db, nickname="失主小李", email="alice@findstar.demo", password="User@2026", role=UserRole.user.value
        )
        bob = _get_or_create_user(
            db, nickname="拾获者小王", email="bob@findstar.demo", password="User@2026", role=UserRole.user.value
        )

        now = utcnow()

        # 正样本 1：黑色无线耳机（教学楼）
        _create_lost(
            db, alice.id,
            title="黑色无线耳机", description="黑色无线耳机，可能落在教学楼，耳机盒上有轻微划痕",
            category="电子产品", color="黑色", brand=None,
            location_code="教学楼", location_text="教学楼二楼教室",
            lost_at=now - timedelta(days=2),
        )
        _create_found(
            db, bob.id,
            title="教学楼二楼拾获黑色耳机盒", description="在教学楼二楼教室捡到一个黑色无线耳机充电盒",
            category="电子产品", color="黑色", brand=None,
            location_code="教学楼", location_text="教学楼二楼",
            found_at=now - timedelta(days=1),
        )
        # 正样本 2：蓝色雨伞（图书馆）
        _create_lost(
            db, alice.id,
            title="蓝色校园雨伞", description="蓝色折叠伞，图书馆附近遗失，伞柄有一圈白色贴纸",
            category="雨具", color="蓝色", brand=None,
            location_code="图书馆", location_text="图书馆一楼大厅",
            lost_at=now - timedelta(days=5),
        )
        _create_found(
            db, bob.id,
            title="图书馆门口发现蓝色折叠伞", description="图书馆门口发现一把蓝色折叠伞",
            category="雨具", color="蓝色", brand=None,
            location_code="图书馆", location_text="图书馆门口",
            found_at=now - timedelta(days=4),
        )
        # 正样本 3：银色水杯（食堂）
        _create_lost(
            db, alice.id,
            title="带卡通贴纸的银色水杯", description="银色保温杯，杯身贴有卡通贴纸，食堂附近遗失",
            category="水杯餐具", color="银色", brand=None,
            location_code="食堂", location_text="食堂一楼",
            lost_at=now - timedelta(days=3),
        )
        _create_found(
            db, bob.id,
            title="食堂附近捡到银色保温杯", description="食堂附近捡到银色保温杯，杯身有贴纸",
            category="水杯餐具", color="银色", brand=None,
            location_code="食堂", location_text="食堂门口",
            found_at=now - timedelta(days=2),
        )
        # 负样本 1：蓝色长柄雨伞（与耳机类别冲突）
        _create_found(
            db, bob.id,
            title="蓝色长柄雨伞", description="校园内捡到一把蓝色长柄雨伞",
            category="雨具", color="蓝色", brand=None,
            location_code="操场", location_text="操场看台",
            found_at=now - timedelta(days=1),
        )
        # 负样本 2：黑色耳机盒（与雨伞冲突）
        _create_found(
            db, bob.id,
            title="黑色耳机盒", description="收到一个黑色耳机盒，无其他特征",
            category="数码配件", color="黑色", brand=None,
            location_code="未知", location_text="未记录具体地点",
            found_at=None,
        )
        # 信息不足样本
        _create_lost(
            db, alice.id,
            title="学生卡", description="学生卡丢失，具体时间地点记不清了",
            category="证件卡类", color=None, brand=None,
            location_code="未知", location_text="不清楚",
            lost_at=None,
        )

        db.commit()
        print("[seed] 演示数据写入完成。")
        print(f"[seed] 管理员：{admin_email}")
        print("[seed] 普通用户：alice@findstar.demo / bob@findstar.demo（密码 User@2026）")
    finally:
        db.close()


if __name__ == "__main__":
    main()