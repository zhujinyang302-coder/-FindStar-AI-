"""认证接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import UnauthorizedError
from app.core.security import create_access_token, verify_password
from app.db.enums import UserStatus
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, LoginResponse, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.execute(
        select(User).where(User.email == payload.email)
    ).scalars().first()
    # 统一错误信息，避免账号枚举
    if user is None or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("账号或密码错误")
    if user.status != UserStatus.active.value:
        raise UnauthorizedError("账号已被禁用")

    token = create_access_token(user.id, user.role)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserPublic(id=user.id, nickname=user.nickname, role=user.role),
    )