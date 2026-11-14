"""通知 Schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: str
    ref_type: str | None = None
    ref_id: int | None = None
    is_read: bool
    created_at: datetime


class NotificationListOut(BaseModel):
    items: list[NotificationOut] = Field(default_factory=list)
    total: int = 0
    unread_count: int = 0


class UnreadCountOut(BaseModel):
    unread_count: int