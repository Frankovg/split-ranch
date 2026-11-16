"""Running balance, payment suggestions and payments."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

from split_ranch.api.deps import GroupActorDep, IfMatchDep, SessionDep, etag
from split_ranch.schemas.common import Page
from split_ranch.schemas.payments import (
    GroupBalanceRead,
    PaymentCreate,
    PaymentDispute,
    PaymentNote,
    PaymentRead,
)
from split_ranch.use_cases import balance, payments

router = APIRouter(prefix="/groups/{group_id}", tags=["payments"])

PaymentStatus = Literal["sent", "confirmed", "disputed", "cancelled"]


@router.get("/balance")
def get_balance(actor: GroupActorDep, session: SessionDep) -> GroupBalanceRead:
    return balance.get_balance(session, actor)


@router.get("/payments")
def list_payments(
    actor: GroupActorDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
    status: Annotated[list[PaymentStatus] | None, Query()] = None,
) -> Page[PaymentRead]:
    items, next_cursor = payments.list_payments(
        session, actor, limit=limit, cursor=cursor, status=list(status) if status else None
    )
    return Page[PaymentRead](items=items, next_cursor=next_cursor)


@router.post("/payments", status_code=201, response_model=PaymentRead)
def record_payment(data: PaymentCreate, actor: GroupActorDep, session: SessionDep) -> JSONResponse:
    """The payer records `sent`; the receiver records `confirmed` (cash received)."""
    status, result = payments.record_payment(session, actor, data)
    return JSONResponse(
        result.model_dump(mode="json"), status_code=status, headers=etag(result.version)
    )


@router.get("/payments/{payment_id}")
def get_payment(
    payment_id: UUID, actor: GroupActorDep, session: SessionDep, response: Response
) -> PaymentRead:
    result = payments.get_payment(session, actor, payment_id)
    response.headers.update(etag(result.version))
    return result


def _transition(
    action: str,
    payment_id: UUID,
    data: PaymentNote | PaymentDispute,
    actor: GroupActorDep,
    session: SessionDep,
    if_match: int | None,
    response: Response,
) -> PaymentRead:
    result = payments.transition_payment(session, actor, payment_id, action, data, if_match)
    response.headers.update(etag(result.version))
    return result


@router.post("/payments/{payment_id}/confirm")
def confirm_payment(
    payment_id: UUID,
    actor: GroupActorDep,
    session: SessionDep,
    if_match: IfMatchDep,
    response: Response,
    data: PaymentNote | None = None,
) -> PaymentRead:
    """Receiver only."""
    return _transition(
        "confirm", payment_id, data or PaymentNote(), actor, session, if_match, response
    )


@router.post("/payments/{payment_id}/dispute")
def dispute_payment(
    payment_id: UUID,
    data: PaymentDispute,
    actor: GroupActorDep,
    session: SessionDep,
    if_match: IfMatchDep,
    response: Response,
) -> PaymentRead:
    """Receiver only; a note is required."""
    return _transition("dispute", payment_id, data, actor, session, if_match, response)


@router.post("/payments/{payment_id}/cancel")
def cancel_payment(
    payment_id: UUID,
    actor: GroupActorDep,
    session: SessionDep,
    if_match: IfMatchDep,
    response: Response,
    data: PaymentNote | None = None,
) -> PaymentRead:
    """Payer only, while the payment is sent or disputed."""
    return _transition(
        "cancel", payment_id, data or PaymentNote(), actor, session, if_match, response
    )
