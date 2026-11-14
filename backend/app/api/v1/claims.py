"""旧认领路由已下线。

认领与归还线索统一迁移至 `/contact-requests`；旧路径由
`app/api/v1/legacy.py` 返回 410。本模块不再注册任何路由。
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/claims", tags=["claims-legacy"])