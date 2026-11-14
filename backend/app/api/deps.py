"""API 依赖：数据库会话与身份/角色校验。

所有私有接口的 user_id 均从登录身份推导，绝不信任前端传入的操作者标识。
"""

from __future__ import annotations

import jwt
from fastapi import Depends, Header, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.enums import ItemType, UserRole, UserStatus
from app.db.models import ContactRequest, MatchBatch, User
from app.db.session import get_db
from app.services import audit
from app.services.item_service import _model  # noqa: PLC2701


def get_bearer_token(authorization: str | None = Header(default=None)) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def get_current_user(
    token: str | None = Depends(get_bearer_token),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise UnauthorizedError("请先登录")
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("登录凭证已过期") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("登录凭证无效") from exc

    user = db.get(User, int(payload.get("sub", 0)))
    if user is None or user.status != UserStatus.active.value:
        raise UnauthorizedError("账号不可用")
    return user


def get_optional_user(
    token: str | None = Depends(get_bearer_token),
    db: Session = Depends(get_db),
) -> User | None:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return None
    user = db.get(User, int(payload.get("sub", 0)))
    if user is None or user.status != UserStatus.active.value:
        return None
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin.value:
        raise ForbiddenError("需要管理员权限")
    return user

def require_non_admin(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """匹配/候选/申请域统一依赖：管理员一律 403 并留痕。"""
    if user.role == UserRole.admin.value:
        audit.record_audit(
            db,
            actor_id=user.id,
            action="admin_match_denied",
            entity_type="user",
            entity_id=user.id,
            details={"reason": "admin_not_allowed_on_match_domain"},
        )
        db.commit()
        raise ForbiddenError("管理员不参与匹配流程", code="ADMIN_NOT_ALLOWED")
    return user


def get_owned_item(
    item_type: str = Path(..., pattern="^(lost|found)$"),
    item_id: int = Path(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
) -> dict:
    """读取本人记录；非本人统一 404（管理员已在上游 403）。"""
    model = _model(item_type)
    item = db.get(model, item_id)
    if item is None or item.user_id != user.id:
        raise NotFoundError("记录不存在")
    return {"item_type": item_type, "item_id": item_id, "item": item}


def get_owned_batch(
    batch_id: str = Path(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
) -> MatchBatch:
    batch = db.execute(
        select(MatchBatch).where(
            MatchBatch.batch_id == batch_id,
            MatchBatch.initiator_id == user.id,
        )
    ).scalars().first()
    if batch is None:
        raise NotFoundError("匹配批次不存在")
    return batch


def get_request_party(
    request_id: int = Path(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ContactRequest:
    if user.role == UserRole.admin.value:
        raise NotFoundError("申请不存在")
    request = db.get(ContactRequest, request_id)
    if request is None or (
        request.applicant_id != user.id and request.target_owner_id != user.id
    ):
        raise NotFoundError("申请不存在")
    return request


def get_item_type(item_type: str = Path(..., pattern="^(lost|found)$")) -> str:
    return item_type