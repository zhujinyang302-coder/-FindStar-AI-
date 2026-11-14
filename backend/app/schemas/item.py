"""物品记录 Schema（V3）：发布、更新、本人记录输出（字段白名单）。

公开输出严禁包含：联系电话、学号、邮箱等私密字段。
对侧信息在 MyItem* DTO 结构上不存在。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.timeutil import utcnow
from app.db.enums import ITEM_CATEGORIES, UNKNOWN

_SCRIPT_PATTERN = re.compile(r"<\s*script|javascript:|on\w+\s*=", re.IGNORECASE)


def sanitize_text(value: str) -> str:
    """基础输入防护：拒绝明显的脚本/注入载荷。"""
    if _SCRIPT_PATTERN.search(value):
        raise ValueError("输入包含不允许的脚本内容")
    return value.strip()


def _normalize_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    if value > utcnow():
        raise ValueError("时间不得晚于当前时刻")
    return value


class ItemCreateBase(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=5000)
    category: str = Field(min_length=1, max_length=50)
    color: str | None = Field(default=None, max_length=40)
    brand: str | None = Field(default=None, max_length=80)
    location_code: str | None = Field(default=None, max_length=100)
    location_text: str = Field(min_length=1, max_length=200)
    occurred_at: datetime | None = None
    image_keys: list[str] = Field(default_factory=list, max_length=5)
    matching_notice_accepted: bool = False

    @field_validator("title", "description", "location_text")
    @classmethod
    def _no_script(cls, v: str) -> str:
        return sanitize_text(v)

    @field_validator("color", "brand", "location_code")
    @classmethod
    def _optional_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("category")
    @classmethod
    def _category_in_enum(cls, v: str) -> str:
        v = v.strip()
        if v not in ITEM_CATEGORIES:
            raise ValueError(f"类别不在受控范围内：{v}")
        return v

    @field_validator("occurred_at")
    @classmethod
    def _time_valid(cls, v: datetime | None) -> datetime | None:
        return _normalize_time(v)

    @field_validator("image_keys")
    @classmethod
    def _image_keys_clean(cls, v: list[str]) -> list[str]:
        cleaned = [key.strip() for key in v if key and key.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("图片 key 不得重复")
        return cleaned

    @model_validator(mode="after")
    def _info_sufficient_shape(self) -> "ItemCreateBase":
        # 跨字段信息量校验在服务层执行，以便返回 INSUFFICIENT_INFO 业务码；
        # 此处只校验基本形状，避免把业务码降级为通用校验错误。
        return self

    @property
    def info_sufficient(self) -> bool:
        return bool(self.image_keys) or len(self.description.strip()) >= 20


class LostItemCreate(ItemCreateBase):
    pass


class FoundItemCreate(ItemCreateBase):
    pass


class ItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    color: str | None = Field(default=None, max_length=40)
    brand: str | None = Field(default=None, max_length=80)
    location_code: str | None = Field(default=None, max_length=100)
    location_text: str | None = Field(default=None, min_length=1, max_length=200)
    occurred_at: datetime | None = None
    image_keys: list[str] | None = Field(default=None, max_length=5)

    @field_validator("title", "description", "location_text")
    @classmethod
    def _no_script(cls, v: str | None) -> str | None:
        return sanitize_text(v) if v is not None else None

    @field_validator("category")
    @classmethod
    def _category_in_enum(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if v not in ITEM_CATEGORIES:
            raise ValueError(f"类别不在受控范围内：{v}")
        return v

    @field_validator("occurred_at")
    @classmethod
    def _time_valid(cls, v: datetime | None) -> datetime | None:
        return _normalize_time(v)


class ImageOut(BaseModel):
    id: int
    object_key: str
    url: str
    mime_type: str
    size_bytes: int


class LatestReviewOut(BaseModel):
    status: str
    opinion: str | None = None
    decided_at: datetime | None = None


class MatchSummaryOut(BaseModel):
    last_batch_id: str | None = None
    candidate_count: int = 0
    degraded: bool = False
    expires_at: datetime | None = None


class ContactSummaryOut(BaseModel):
    pending_received: int = 0


class MyItemOut(BaseModel):
    """发布/修改后的最小输出。"""

    id: int
    type: str
    status: str
    info_sufficient: bool
    review_ticket_no: str | None = None
    data_version: int = 1
    created_at: datetime


class MyItemListItem(BaseModel):
    id: int
    type: str
    title: str
    category: str
    status: str
    review_round: int
    latest_review: LatestReviewOut | None = None
    match_summary: MatchSummaryOut | None = None
    contact_summary: ContactSummaryOut | None = None
    cover_image: str | None = None
    created_at: datetime
    updated_at: datetime


class MyItemListOut(BaseModel):
    items: list[MyItemListItem]
    total: int
    page: int
    page_size: int


class MyItemDetailOut(BaseModel):
    id: int
    type: str
    title: str
    description: str
    category: str
    color: str | None
    brand: str | None
    location_code: str
    location_text: str
    occurred_at: datetime | None
    status: str
    info_sufficient: bool
    review_round: int
    can_match: bool
    can_edit: bool
    can_withdraw: bool
    can_request_delist: bool
    latest_review: LatestReviewOut | None = None
    images: list[ImageOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WithdrawOut(BaseModel):
    item_id: int
    status: str
    ticket_status: str


# ---------- 兼容旧详情的白名单输出（仅发布者本人可读） ----------
class ItemOut(BaseModel):
    id: int
    type: str
    title: str
    description: str
    category: str
    color: str | None
    brand: str | None
    location_code: str
    location_text: str
    occurred_at: datetime | None
    status: str
    owner_nickname: str
    is_owner: bool
    can_claim: bool
    created_at: datetime
    images: list[ImageOut] = []


class ItemListItem(BaseModel):
    id: int
    type: str
    title: str
    category: str
    color: str | None
    location_text: str
    occurred_at: datetime | None
    status: str
    created_at: datetime
    cover_image: str | None


class ItemListOut(BaseModel):
    items: list[ItemListItem]
    total: int
    page: int
    page_size: int


def normalize_location_code(value: str | None) -> str:
    if not value or not value.strip():
        return UNKNOWN
    return value.strip()