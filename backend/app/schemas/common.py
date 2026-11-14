"""通用 Schema：分页与基础响应。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=50)


class Paginated(BaseModel):
    total: int
    page: int
    page_size: int


class MessageOut(BaseModel):
    message: str = "ok"