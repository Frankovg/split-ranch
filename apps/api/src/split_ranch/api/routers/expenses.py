"""Expenses."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Header, Query, Response
from fastapi.responses import JSONResponse

from split_ranch.api.deps import HouseholdActorDep, IfMatchDep, SessionDep, etag
from split_ranch.schemas.common import Page, ReasonIn
from split_ranch.schemas.expenses import (
    AdjustmentCreate,
    AdjustmentRead,
    ExpenseCreate,
    ExpenseDeleteIn,
    ExpensePreviewIn,
    ExpenseRead,
    ExpenseUpdate,
    RevisionRead,
    SplitPreviewRead,
)
from split_ranch.use_cases import expenses

router = APIRouter(prefix="/households/{household_id}/expenses", tags=["expenses"])

IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=64)]


@router.get("")
def list_expenses(
    actor: HouseholdActorDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
    # A period number or "current" (the latest period).
    period: Annotated[str | None, Query(pattern=r"^(current|[1-9][0-9]{0,6})$")] = None,
    category_id: UUID | None = None,
    payer_member_id: UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: Literal["draft", "confirmed"] | None = None,
) -> Page[ExpenseRead]:
    items, next_cursor = expenses.list_expenses(
        session,
        actor,
        limit=limit,
        cursor=cursor,
        period=None if period is None else "current" if period == "current" else int(period),
        category_id=category_id,
        payer_member_id=payer_member_id,
        q=q,
        status=status,
    )
    return Page[ExpenseRead](items=items, next_cursor=next_cursor)


@router.post("", status_code=201, response_model=ExpenseRead)
def create_expense(
    data: ExpenseCreate,
    actor: HouseholdActorDep,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    result = expenses.create_expense(session, actor, data, idempotency_key=idempotency_key)
    return JSONResponse(result.body, status_code=result.status, headers=etag(result.version))


@router.post("/preview")
def preview_expense(
    data: ExpensePreviewIn, actor: HouseholdActorDep, session: SessionDep
) -> SplitPreviewRead:
    return expenses.preview_split(session, actor, data)


@router.get("/{expense_id}")
def get_expense(
    expense_id: UUID, actor: HouseholdActorDep, session: SessionDep, response: Response
) -> ExpenseRead:
    result = expenses.get_expense(session, actor, expense_id)
    response.headers.update(etag(result.version))
    return result


@router.patch("/{expense_id}")
def update_expense(
    expense_id: UUID,
    data: ExpenseUpdate,
    actor: HouseholdActorDep,
    session: SessionDep,
    if_match: IfMatchDep,
    response: Response,
) -> ExpenseRead:
    result = expenses.update_expense(session, actor, expense_id, data, if_match)
    response.headers.update(etag(result.version))
    return result


@router.delete("/{expense_id}", status_code=204)
def delete_expense(
    expense_id: UUID,
    actor: HouseholdActorDep,
    session: SessionDep,
    if_match: IfMatchDep,
    data: Annotated[ExpenseDeleteIn | None, Body()] = None,
) -> Response:
    expenses.delete_expense(session, actor, expense_id, data or ExpenseDeleteIn(), if_match)
    return Response(status_code=204)


@router.post("/{expense_id}/confirm")
def confirm_expense(
    expense_id: UUID,
    actor: HouseholdActorDep,
    session: SessionDep,
    if_match: IfMatchDep,
    response: Response,
    data: Annotated[ReasonIn | None, Body()] = None,
) -> ExpenseRead:
    result = expenses.confirm_draft(
        session, actor, expense_id, (data or ReasonIn()).reason, if_match
    )
    response.headers.update(etag(result.version))
    return result


@router.post("/{expense_id}/adjustments", status_code=201)
def create_adjustment(
    expense_id: UUID, data: AdjustmentCreate, actor: HouseholdActorDep, session: SessionDep
) -> AdjustmentRead:
    return expenses.create_adjustment(session, actor, expense_id, data)


@router.get("/{expense_id}/revisions")
def list_revisions(
    expense_id: UUID, actor: HouseholdActorDep, session: SessionDep
) -> list[RevisionRead]:
    return expenses.list_revisions(session, actor, expense_id)
