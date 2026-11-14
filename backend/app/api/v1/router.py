"""聚合 API v1 路由。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin_quality,
    admin_records,
    admin_review,
    ai,
    auth,
    contacts,
    drafts,
    images,
    items,
    legacy,
    matches,
    notifications,
    public,
)

api_router = APIRouter()
api_router.include_router(public.router)
api_router.include_router(auth.router)
api_router.include_router(items.router)
api_router.include_router(drafts.router)
api_router.include_router(images.router)
api_router.include_router(ai.router)
api_router.include_router(matches.router)
api_router.include_router(contacts.router)
api_router.include_router(notifications.router)
api_router.include_router(admin_review.router)
api_router.include_router(admin_records.router)
api_router.include_router(admin_quality.router)
api_router.include_router(legacy.router)