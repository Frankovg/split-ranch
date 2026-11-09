"""Periods, balance, settlement and transfers."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Path, Query

from split_ranch.api.deps import HouseholdActorDep, IfMatchDep, SessionDep
from split_ranch.schemas.common import Page, PeriodSeq
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
from split_ranch.use_cases.periods import PeriodKey

router = APIRouter(prefix="/households/{household_id}", tags=["periods"])

# A period number (1, 2, ...) or "current" for the latest period.
PeriodPath = Annotated[str, Path(pattern=r"^(current|[1-9][0-9]{0,6})$")]


def _key(value: str) -> PeriodKey:
    return "current" if value == "current" else int(value)


@router.get("/periods")
def list_periods(
    actor: HouseholdActorDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 24,
    cursor: Annotated[PeriodSeq | None, Query()] = None,
) -> Page[PeriodRead]:
    items, next_cursor = periods.list_periods(session, actor, limit=limit, before=cursor)
    return Page[PeriodRead](items=items, next_cursor=next_cursor)


@router.post("/periods", status_code=201)
def start_period(actor: HouseholdActorDep, session: SessionDep) -> PeriodRead:
    return periods.start_period(session, actor)


@router.get("/periods/{period}")
def get_period(period: PeriodPath, actor: HouseholdActorDep, session: SessionDep) -> PeriodRead:
    return periods.get_period(session, actor, _key(period))


@router.get("/periods/{period}/balance")
def get_balance(
    period: PeriodPath, actor: HouseholdActorDep, session: SessionDep
) -> PeriodBalanceRead:
    return periods.get_balance(session, actor, _key(period))


@router.post("/periods/{period}/close")
def close_period(
    period: PeriodPath, actor: HouseholdActorDep, session: SessionDep, if_match: IfMatchDep
) -> PeriodRead:
    return periods.close_period(session, actor, _key(period), if_match)


@router.post("/periods/{period}/reopen")
def reopen_period(
    period: PeriodPath, data: ReopenIn, actor: HouseholdActorDep, session: SessionDep
) -> PeriodRead:
    return periods.reopen_period(session, actor, _key(period), data)


@router.get("/periods/{period}/settlement")
def get_settlement(
    period: PeriodPath, actor: HouseholdActorDep, session: SessionDep
) -> SettlementRead:
    return periods.get_settlement(session, actor, _key(period))


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
