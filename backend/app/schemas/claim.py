"""认领申请 Schema。

私密核验信息（private_evidence）仅用于审核，绝不进入公开响应或普通日志。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ClaimCreate(BaseModel):
    match_id: int | None = None
    lost_item_id: int | None = None
    found_item_id: int | None = None
    private_evidence: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _target_present(self) -> "ClaimCreate":
        if self.match_id is None and self.lost_item_id is None and self.found_item_id is None:
            raise ValueError("必须提供 match_id 或目标记录 ID")
        return self


class ClaimOut(BaseModel):
    """对外输出（不含私密核验信息）。"""

    id: int
    match_id: int | None
    target_type: str
    target_item_id: int
    target_title: str
    review_status: str
    review_note: str | None
    created_at: datetime
    reviewed_at: datetime | None


class ClaimListOut(BaseModel):
    items: list[ClaimOut]
    total: int