"""管理端记录管理 DTO（结构上不含匹配域与联系方式）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AdminRecordListItem(BaseModel):
    item_type: str
    item_id: int
    title: str
    category: str
    color: str | None = None
    location_text: str
    occurred_at: datetime | None = None
    status: str
    created_at: datetime
    is_removed: bool = False
    has_pending_delist: bool = False


class AdminRecordListOut(BaseModel):
    items: list[AdminRecordListItem]
    total: int
    page: int
    page_size: int


class AdminRecordImage(BaseModel):
    id: int
    url: str | None = None
    thumb_url: str | None = None
    sensitive_masked: bool = False


class AdminReviewBrief(BaseModel):
    review_round: int
    status: str
    opinion: str | None = None
    decided_at: datetime | None = None


class AdminRecordDetailOut(BaseModel):
    item_type: str
    item_id: int
    title: str
    category: str
    color: str | None = None
    brand: str | None = None
    location_text: str
    location_code: str | None = None
    occurred_at: datetime | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    info_sufficient: bool
    review_round: int
    description: str
    images: list[AdminRecordImage] = Field(default_factory=list)
    history: list[AdminReviewBrief] = Field(default_factory=list)


class AdminDelistRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class AdminDelistOut(BaseModel):
    ticket_no: str
    item_status: str
    decided_at: datetime
    invalidated_batches: int
    affected_requests: int = 0