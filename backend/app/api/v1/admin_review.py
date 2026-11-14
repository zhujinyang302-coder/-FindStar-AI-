"""管理端上下架审核接口（仅管理员）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.models import User
from app.db.session import get_db
from app.schemas.admin import (
    ReviewDecisionOut,
    ReviewDecisionRequest,
    ReviewQueueOut,
    ReviewTicketDetailOut,
)
from app.services import review_service

router = APIRouter(prefix="/admin/review", tags=["admin-review"])


@router.get("/tickets", response_model=ReviewQueueOut)
def list_tickets(
    review_type: str | None = Query(default=None, pattern="^(listing|delisting)$"),
    source: str | None = Query(default=None),
    overdue: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ReviewQueueOut:
    return review_service.list_tickets(
        db,
        review_type=review_type,
        source=source,
        overdue=overdue,
        page=page,
        page_size=page_size,
    )


@router.get("/history", response_model=ReviewQueueOut)
def review_history(
    review_type: str | None = Query(default=None, pattern="^(listing|delisting)$"),
    source: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ReviewQueueOut:
    return review_service.list_tickets(
        db,
        review_type=review_type,
        source=source,
        overdue=None,
        page=page,
        page_size=page_size,
        history=True,
    )


@router.get("/tickets/{ticket_no}", response_model=ReviewTicketDetailOut)
def ticket_detail(
    ticket_no: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ReviewTicketDetailOut:
    return review_service.get_ticket(db, ticket_no)


@router.post("/tickets/{ticket_no}/decide", response_model=ReviewDecisionOut)
def decide(
    ticket_no: str,
    payload: ReviewDecisionRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ReviewDecisionOut:
    return review_service.decide(
        db,
        admin=admin,
        ticket_no=ticket_no,
        decision=payload.decision,
        opinion=payload.opinion,
    )