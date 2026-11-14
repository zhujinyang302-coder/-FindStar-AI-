"""健康探测：存活（无需鉴权）与就绪（检查依赖）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cache import get_cache
from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict:
    return {"status": "alive"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    dependencies: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        dependencies["database"] = "ok"
    except Exception:  # noqa: BLE001
        dependencies["database"] = "unavailable"

    cache = get_cache()
    dependencies["cache"] = "ok" if cache.available else "degraded"

    ready_state = dependencies["database"] == "ok"
    return {
        "status": "ready" if ready_state else "not_ready",
        "dependencies": dependencies,
    }