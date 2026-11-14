"""双向联系申请 Schema（认领 / 归还线索）。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.match import CandidateSummaryOut


class ContactCreateRequest(BaseModel):
    batch_id: str = Field(min_length=1, max_length=64)
    candidate_public_id: str = Field(min_length=1, max_length=64)
    request_type: Literal["claim", "return_clue"]
    private_verification: str | None = Field(default=None, max_length=500)
    handover_location_code: str | None = Field(default=None, max_length=100)
    handover_window_start: datetime | None = None
    handover_window_end: datetime | None = None
    handover_note: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _verification_rules(self) -> "ContactCreateRequest":
        value = (self.private_verification or "").strip()
        if self.request_type == "claim" and len(value) < 10:
            raise ValueError("认领申请的私密核验信息需不少于 10 字")
        if self.handover_window_start and self.handover_window_end:
            if self.handover_window_end <= self.handover_window_start:
                raise ValueError("交接结束时间必须晚于开始时间")
        return self


class ContactRequestOut(BaseModel):
    id: int
    request_type: str
    target_item_type: str
    target_item_id: int
    status: str
    disclosure_level: str = "verified"
    created_at: datetime


class ContactRequestListItem(BaseModel):
    id: int
    request_type: str
    batch_id: str
    candidate_public_id: str
    target_item_type: str
    target_item_id: int
    status: str
    created_at: datetime
    decided_at: datetime | None = None


class ContactRequestListOut(BaseModel):
    items: list[ContactRequestListItem] = Field(default_factory=list)
    total: int = 0


class ReceivedContactItem(BaseModel):
    id: int
    request_type: str
    target_item_title: str
    candidate_summary: CandidateSummaryOut | None = None
    private_verification: str | None = None
    handover_location_code: str | None = None
    handover_window_start: datetime | None = None
    handover_window_end: datetime | None = None
    handover_note: str | None = None
    status: str
    sensitive_category: bool = False
    created_at: datetime


class ReceivedContactListOut(BaseModel):
    items: list[ReceivedContactItem] = Field(default_factory=list)
    total: int = 0


class ContactRequestDetailOut(BaseModel):
    id: int
    request_type: str
    batch_id: str
    candidate_public_id: str
    target_item_type: str
    target_item_id: int
    target_item_title: str
    status: str
    private_verification: str | None = None
    handover_location_code: str | None = None
    handover_window_start: datetime | None = None
    handover_window_end: datetime | None = None
    handover_note: str | None = None
    decision_note: str | None = None
    failure_count: int = 0
    cooldown_until: datetime | None = None
    sensitive_category: bool = False
    created_at: datetime
    decided_at: datetime | None = None
    candidate_summary: CandidateSummaryOut | None = None


class ContactConfirmRequest(BaseModel):
    handover_location_code: str = Field(min_length=1, max_length=100)
    handover_window_start: datetime
    handover_window_end: datetime
    handover_note: str | None = Field(default=None, max_length=200)
    sensitive_verified: bool = False

    @model_validator(mode="after")
    def _window(self) -> "ContactConfirmRequest":
        if self.handover_window_end <= self.handover_window_start:
            raise ValueError("交接结束时间必须晚于开始时间")
        return self


class ContactRejectRequest(BaseModel):
    decision_note: str = Field(min_length=5, max_length=200)


class ContactConfirmOut(BaseModel):
    id: int
    status: str
    target_item_status: str
    initiated_item_status: str
    disclosure_level: str = "handover"
    invalidated_batches: int = 0
    notified_users: int = 0