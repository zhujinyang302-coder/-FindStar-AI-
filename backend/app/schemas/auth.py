"""认证相关 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    """对外可见的用户信息（白名单，不含邮箱/联系方式）。"""

    id: int
    nickname: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic