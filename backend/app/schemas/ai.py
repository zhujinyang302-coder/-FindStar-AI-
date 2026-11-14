"""AI Schema：结构化物品特征（模型输出必须经此校验）。

字段无法识别时置为 None / "未知"，绝不伪造。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.db.enums import ITEM_CATEGORIES, UNKNOWN


class ItemFeatures(BaseModel):
    model_config = {"extra": "ignore"}

    category: str = UNKNOWN
    color: str | None = None
    brand: str | None = None
    visible_features: list[str] = Field(default_factory=list)
    description: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    unknown_fields: list[str] = Field(default_factory=list)

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, v: object) -> str:
        if not isinstance(v, str) or not v.strip():
            return UNKNOWN
        value = v.strip()
        if value in ITEM_CATEGORIES:
            return value
        # 尝试模糊匹配已知类别关键字
        for category in ITEM_CATEGORIES:
            if category in value or value in category:
                return category
        return UNKNOWN

    @field_validator("color", "brand", mode="before")
    @classmethod
    def _normalize_optional(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            value = v.strip()
            if not value or value.lower() in {"unknown", "未知", "null", "none"}:
                return None
            return value[:40]
        return None

    @field_validator("visible_features", mode="before")
    @classmethod
    def _normalize_features(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [part.strip() for part in v.replace("；", ";").split(";") if part.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()][:20]
        return []

    @field_validator("unknown_fields", mode="before")
    @classmethod
    def _normalize_unknown(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(item) for item in v]
        return []


class ExtractFeaturesRequest(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    image_keys: list[str] = Field(default_factory=list, max_length=5)
    category_hint: str | None = Field(default=None, max_length=50)


class ExtractFeaturesResponse(BaseModel):
    features: ItemFeatures
    warnings: list[str] = Field(default_factory=list)
    provider: str
    degraded: bool
    degraded_reason: str | None = None