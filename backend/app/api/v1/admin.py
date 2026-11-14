"""旧管理端路由已下线。

审核能力迁移至 `/admin/review/*`，质量指标迁移至 `/admin/quality/*`；
所有旧路径由 `app/api/v1/legacy.py` 返回 410。本模块不再注册任何路由。
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin-legacy"])