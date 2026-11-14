"""已下线旧接口的 410 壳路由。

处理器不打开数据库会话、不产生任何副作用；`GET /items/{id}` 保留
"仅发布者本人可见"的旧链接兼容跳转。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_optional_user
from app.core.response import GoneError, NotFoundError
from app.db.enums import UserRole
from app.db.models import User
from app.db.session import get_db
from app.schemas.item import ItemOut
from app.services import item_service

router = APIRouter(tags=["legacy"])

_ITEMS_HINT = "已改为按需匹配：请上传本人记录后发起匹配"
_SEARCH_HINT = "全局检索已下线，请使用匹配结果页的候选内筛选"
_STATS_HINT = "公开统计仅保留聚合完成数：/api/v1/public/stats"
_CLAIM_HINT = "认领已改为 /contact-requests，并新增归还线索"
_ADMIN_HINT = "管理员仅负责上下架审核：/api/v1/admin/review/tickets"


@router.get("/items", deprecated=True)
def legacy_list_items() -> None:
    raise GoneError(_ITEMS_HINT)


@router.get("/search", deprecated=True)
def legacy_search() -> None:
    raise GoneError(_SEARCH_HINT)


@router.get("/stats/overview", deprecated=True)
def legacy_stats() -> None:
    raise GoneError(_STATS_HINT)


@router.patch("/items/{item_type}/{item_id}", deprecated=True)
def legacy_update_item(item_type: str, item_id: int) -> None:
    raise GoneError("记录修改已改为 /api/v1/my/items/{type}/{id}")


@router.get("/matches/{match_id}", deprecated=True)
def legacy_match_detail(match_id: int) -> None:
    raise GoneError("单条匹配结果已下线，请使用 /api/v1/matches/batches/{batch_id}")


@router.post("/claims", deprecated=True)
def legacy_create_claim() -> None:
    raise GoneError(_CLAIM_HINT)


@router.get("/claims/me", deprecated=True)
def legacy_my_claims() -> None:
    raise GoneError(_CLAIM_HINT)


@router.get("/admin/claims", deprecated=True)
def legacy_admin_claims() -> None:
    raise GoneError(_ADMIN_HINT)


@router.get("/admin/claims/{claim_id}", deprecated=True)
def legacy_admin_claim_detail(claim_id: int) -> None:
    raise GoneError(_ADMIN_HINT)


@router.patch("/admin/claims/{claim_id}", deprecated=True)
def legacy_admin_claim_review(claim_id: int) -> None:
    raise GoneError(_ADMIN_HINT)


@router.get("/admin/statistics", deprecated=True)
def legacy_admin_statistics() -> None:
    raise GoneError("运营大盘已下线，匹配指标见 /api/v1/admin/quality/metrics")


@router.post("/admin/items/{item_type}/{item_id}/remove", deprecated=True)
def legacy_admin_remove_item(item_type: str, item_id: int) -> None:
    raise GoneError("下架必须经下架审核单")


@router.get("/items/{item_id}", response_model=ItemOut, deprecated=True)
def legacy_item_detail(
    item_id: int,
    type: str | None = Query(default=None, pattern="^(lost|found)$"),
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
) -> ItemOut:
    """旧链接兼容：仅发布者本人可见，管理员与其他用户一律 404。"""
    if viewer is None or viewer.role == UserRole.admin.value:
        raise NotFoundError("记录不存在")
    item_type, item = _locate_item(db, item_id, type)
    if item.user_id != viewer.id or item.is_removed:
        raise NotFoundError("记录不存在")
    return item_service.serialize_item(db, item, item_type, viewer_id=viewer.id)


def _locate_item(db: Session, item_id: int, item_type: str | None):
    if item_type in ("lost", "found"):
        return item_type, item_service.get_item(db, item_type, item_id)
    for current_type in ("lost", "found"):
        obj = db.get(item_service._model(current_type), item_id)  # noqa: PLC2701
        if obj is not None:
            return current_type, obj
    raise NotFoundError("记录不存在")