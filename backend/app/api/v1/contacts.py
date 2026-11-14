"""双向联系申请接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_request_party, require_non_admin
from app.db.models import ContactRequest, User
from app.db.session import get_db
from app.schemas.contact import (
    ContactConfirmOut,
    ContactConfirmRequest,
    ContactCreateRequest,
    ContactRejectRequest,
    ContactRequestDetailOut,
    ContactRequestListOut,
    ContactRequestOut,
    ReceivedContactListOut,
)
from app.services import contact_service

router = APIRouter(prefix="/contact-requests", tags=["contacts"])


@router.post("", response_model=ContactRequestOut, status_code=201)
def create_contact_request(
    payload: ContactCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
) -> ContactRequestOut:
    contact, reused = contact_service.submit(db, user=user, payload=payload)
    if reused:
        response.status_code = 200
    return ContactRequestOut(
        id=contact.id,
        request_type=contact.request_type,
        target_item_type=contact.target_item_type,
        target_item_id=contact.target_item_id,
        status=contact.status,
        created_at=contact.created_at,
    )


@router.get("/me", response_model=ContactRequestListOut)
def my_requests(
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
) -> ContactRequestListOut:
    return contact_service.list_me(db, user=user)


@router.get("/received", response_model=ReceivedContactListOut)
def received_requests(
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
) -> ReceivedContactListOut:
    return contact_service.list_received(db, user=user)


@router.get("/{request_id}", response_model=ContactRequestDetailOut)
def contact_detail(
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
    contact: ContactRequest = Depends(get_request_party),
) -> ContactRequestDetailOut:
    return contact_service.get_detail(db, user=user, contact=contact)


@router.post("/{request_id}/confirm", response_model=ContactConfirmOut)
def confirm_request(
    payload: ContactConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
    contact: ContactRequest = Depends(get_request_party),
) -> ContactConfirmOut:
    return contact_service.confirm(db, user=user, contact=contact, payload=payload)


@router.post("/{request_id}/reject", response_model=ContactRequestOut)
def reject_request(
    payload: ContactRejectRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_non_admin),
    contact: ContactRequest = Depends(get_request_party),
) -> ContactRequestOut:
    return contact_service.reject(db, user=user, contact=contact, payload=payload)