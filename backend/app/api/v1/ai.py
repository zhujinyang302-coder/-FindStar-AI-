"""AI 特征提取接口（登录用户、限流）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.provider import AIUnavailableError, get_provider
from app.api.deps import get_current_user
from app.cache import get_cache
from app.core.config import settings
from app.core.response import RateLimitError
from app.db.models import User
from app.db.session import get_db
from app.schemas.ai import ExtractFeaturesRequest, ExtractFeaturesResponse, ItemFeatures
from app.services import image_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/extract-features", response_model=ExtractFeaturesResponse)
def extract_features(
    payload: ExtractFeaturesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExtractFeaturesResponse:
    cache = get_cache()
    count = cache.incr(cache.rate_key(user.id, "ai_extract"), 60)
    if count > settings.ai_rate_limit_per_minute:
        raise RateLimitError()

    image_paths = [image_service.resolve_path(key) for key in payload.image_keys]
    provider = get_provider()
    warnings: list[str] = []
    try:
        features = provider.extract_features(
            description=payload.description, image_paths=image_paths
        )
    except AIUnavailableError as exc:
        # 失败路径：不伪装成功，允许用户手动填写
        features = ItemFeatures(category=payload.category_hint or "未知")
        warnings.append(f"识别失败或超时：{exc}")
        return ExtractFeaturesResponse(
            features=features,
            warnings=warnings,
            provider=provider.name,
            degraded=True,
            degraded_reason=str(exc),
        )

    if provider.degraded:
        warnings.append("当前使用本地降级适配器，未调用真实模型；结果仅供手动确认")
    if features.unknown_fields:
        warnings.append("存在无法识别的字段：" + "、".join(features.unknown_fields))

    return ExtractFeaturesResponse(
        features=features,
        warnings=warnings,
        provider=provider.name,
        degraded=provider.degraded,
        degraded_reason=provider.degraded_reason,
    )