"""FastAPI 应用入口。

装配顺序（由外到内）：CORS → 请求上下文 → 统一响应 → 路由。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.cache import get_cache
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RequestContextMiddleware, UnifiedResponseMiddleware
from app.core.response import register_exception_handlers
from app.jobs import scheduler

setup_logging(settings.log_level)
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = get_cache()
    logger.info(
        "application startup",
        extra={
            "route": "startup",
            "error_category": None,
        },
    )
    if cache.degraded:
        logger.warning("cache degraded: " + cache.degraded_reason)
    if not settings.ai_is_live:
        logger.warning("AI provider degraded (mock/local), real AI not configured")
    scheduler.start_scheduler()
    yield
    scheduler.stop_scheduler()
    logger.info("application shutdown", extra={"route": "shutdown"})


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="寻物星图 FindStar — AI 智能失物招领系统后端 API",
    lifespan=lifespan,
)

app.add_middleware(UnifiedResponseMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health_router)
app.include_router(api_router, prefix=settings.api_prefix)