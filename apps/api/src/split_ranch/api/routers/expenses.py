"""Expenses and the spending summary."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Response
from fastapi.responses import JSONResponse

from split_ranch.api.deps import GroupActorDep, IfMatchDep, SessionDep, etag
from split_ranch.repositories.expenses import ExpenseFilters
from split_ranch.schemas.common import Page
from split_ranch.schemas.expenses import (
    ExpenseCreate,
    ExpenseDeleteIn,
    ExpensePreviewIn,
    ExpenseRead,
    ExpenseUpdate,
    RevisionRead,
    SplitPreviewRead,
    SummaryRead,
)
from split_ranch.use_cases import expenses

router = APIRouter(prefix="/groups/{group_id}", tags=["expenses"])


def expense_filters(
    # `from` is a Python keyword: the parameter is aliased.
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    category_id: UUID | None = None,
    payer_member_id: UUID | None = None,
    created_by_user_id: UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> ExpenseFilters:
    """Filters shared by the list and the summary; dates are inclusive."""
    return ExpenseFilters(
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        payer_member_id=payer_member_id,
        created_by_user_id=created_by_user_id,
        q=q,
    )


FiltersDep = Annotated[ExpenseFilters, Depends(expense_filters)]


@router.get("/expenses")
def list_expenses(
    actor: GroupActorDep,
    session: SessionDep,
    filters: FiltersDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> Page[ExpenseRead]:
    items, next_cursor = expenses.list_expenses(session, actor, filters, limit=limit, cursor=cursor)
    return Page[ExpenseRead](items=items, next_cursor=next_cursor)


@router.get("/summary")
def get_summary(
    actor: GroupActorDep,
    session: SessionDep,
    filters: FiltersDep,
    mine: bool = False,
) -> SummaryRead:
    """Totals per category / payer; `mine=true` sums only the caller's shares."""
    return expenses.get_summary(session, actor, filters, mine=mine)


@router.post("/expenses", status_code=201, response_model=ExpenseRead)
def create_expense(data: ExpenseCreate, actor: GroupActorDep, session: SessionDep) -> JSONResponse:
    result = expenses.create_expense(session, actor, data)
    return JSONResponse(result.body, status_code=result.status, headers=etag(result.version))


@router.post("/expenses/preview")
def preview_expense(
    data: ExpensePreviewIn, actor: GroupActorDep, session: SessionDep
) -> SplitPreviewRead:
    return expenses.preview_split(session, actor, data)


@router.get("/expenses/{expense_id}")
def get_expense(
    expense_id: UUID, actor: GroupActorDep, session: SessionDep, response: Response
) -> ExpenseRead:
    result = expenses.get_expense(session, actor, expense_id)
    response.headers.update(etag(result.version))
    return result


@router.patch("/expenses/{expense_id}")
def update_expense(
    expense_id: UUID,
    data: ExpenseUpdate,
    actor: GroupActorDep,
    session: SessionDep,
    if_match: IfMatchDep,
    response: Response,
) -> ExpenseRead:
    result = expenses.update_expense(session, actor, expense_id, data, if_match)
    response.headers.update(etag(result.version))
    return result


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(
    expense_id: UUID,
    actor: GroupActorDep,
    session: SessionDep,
    if_match: IfMatchDep,
    data: Annotated[ExpenseDeleteIn | None, Body()] = None,
) -> Response:
    expenses.delete_expense(session, actor, expense_id, data or ExpenseDeleteIn(), if_match)
    return Response(status_code=204)


@router.get("/expenses/{expense_id}/revisions")
def list_revisions(
    expense_id: UUID, actor: GroupActorDep, session: SessionDep
) -> list[RevisionRead]:
    return expenses.list_revisions(session, actor, expense_id)
