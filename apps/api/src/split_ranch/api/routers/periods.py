"""Periods, balance, settlement and transfers."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Path, Query

from split_ranch.api.deps import HouseholdActorDep, IfMatchDep, SessionDep
from split_ranch.schemas.common import MonthStr, Page, parse_month
from split_ranch.schemas.expenses import (
    PeriodBalanceRead,
    PeriodRead,
    ReopenIn,
    SettlementRead,
    TransferConfirmIn,
    TransferDisputeIn,
    TransferRead,
    TransferSentIn,
)
from split_ranch.use_cases import periods

router = APIRouter(prefix="/households/{household_id}", tags=["periods"])

MonthPath = Annotated[str, Path(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


@router.get("/periods")
def list_periods(
    actor: HouseholdActorDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 24,
    cursor: MonthStr | None = None,
) -> Page[PeriodRead]:
    items, next_cursor = periods.list_periods(
        session, actor, limit=limit, before=parse_month(cursor) if cursor else None
    )
    return Page[PeriodRead](items=items, next_cursor=next_cursor)


@router.get("/periods/{month}")
def get_period(month: MonthPath, actor: HouseholdActorDep, session: SessionDep) -> PeriodRead:
    return periods.get_period(session, actor, parse_month(month))


@router.get("/periods/{month}/balance")
def get_balance(
    month: MonthPath, actor: HouseholdActorDep, session: SessionDep
) -> PeriodBalanceRead:
    return periods.get_balance(session, actor, parse_month(month))


@router.post("/periods/{month}/close")
def close_period(
    month: MonthPath, actor: HouseholdActorDep, session: SessionDep, if_match: IfMatchDep
) -> PeriodRead:
    return periods.close_period(session, actor, parse_month(month), if_match)


@router.post("/periods/{month}/reopen")
def reopen_period(
    month: MonthPath, data: ReopenIn, actor: HouseholdActorDep, session: SessionDep
) -> PeriodRead:
    return periods.reopen_period(session, actor, parse_month(month), data)


@router.get("/periods/{month}/settlement")
def get_settlement(
    month: MonthPath, actor: HouseholdActorDep, session: SessionDep
) -> SettlementRead:
    return periods.get_settlement(session, actor, parse_month(month))


@router.post("/transfers/{transfer_id}/sent")
def mark_sent(
    transfer_id: UUID,
    actor: HouseholdActorDep,
    session: SessionDep,
    data: Annotated[TransferSentIn | None, Body()] = None,
) -> TransferRead:
    return periods.mark_transfer_sent(session, actor, transfer_id, data or TransferSentIn())


@router.post("/transfers/{transfer_id}/confirm")
def confirm(
    transfer_id: UUID,
    actor: HouseholdActorDep,
    session: SessionDep,
    data: Annotated[TransferConfirmIn | None, Body()] = None,
) -> TransferRead:
    return periods.confirm_transfer(session, actor, transfer_id, data or TransferConfirmIn())


@router.post("/transfers/{transfer_id}/dispute")
def dispute(
    transfer_id: UUID, data: TransferDisputeIn, actor: HouseholdActorDep, session: SessionDep
) -> TransferRead:
    return periods.dispute_transfer(session, actor, transfer_id, data)
