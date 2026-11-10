"""Periods, live balance, close/reopen, snapshots and transfer state machine."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any, Literal
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from split_ranch.core import clock
from split_ranch.core.actor import HouseholdActor
from split_ranch.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from split_ranch.domain import Balance, LedgerExpense, NetEntry, Share, compute_balances, settle
from split_ranch.jobs.queue import enqueue
from split_ranch.models import (
    Household,
    HouseholdMember,
    Period,
    SettlementSnapshot,
    SettlementTransfer,
)
from split_ranch.repositories import expenses as erepo
from split_ranch.repositories import households as hrepo
from split_ranch.schemas.expenses import (
    BalanceRead,
    PeriodBalanceRead,
    PeriodRead,
    ReopenIn,
    SettlementRead,
    SnapshotRead,
    TransferConfirmIn,
    TransferDisputeIn,
    TransferRead,
    TransferSentIn,
)
from split_ranch.use_cases.common import audit, check_version, require_active, require_admin

log = structlog.get_logger(__name__)

PeriodState = Literal["open", "closed", "locked"]
# A period is addressed by its number, or "current" for the latest one.
PeriodKey = int | Literal["current"]


# ------------------------------------------------------------- lifecycle


def create_first_period(session: Session, household: Household) -> Period:
    """A new household starts with period 1 open."""
    period = Period(household_id=household.id, seq=1, status="open", started_at=clock.now())
    session.add(period)
    session.flush()
    return period


def require_open_period(session: Session, household_id: UUID) -> Period:
    """The period new expenses go to. Members start it by hand after closing the last one."""
    period = erepo.get_open_period(session, household_id, for_update=True)
    if period is None:
        raise Conflict("There is no open period: start a new one first", code="no_open_period")
    return period


def period_state(session: Session, period: Period) -> PeriodState:
    if period.status == "open":
        return "open"
    if period.status == "settled" or erepo.period_has_locking_transfer(
        session, period.household_id, period.id
    ):
        return "locked"
    return "closed"


def _member_order(session: Session, household_id: UUID, seq: int) -> list[str]:
    return [str(m.id) for m in hrepo.period_members(session, household_id, seq)]


def compute_period_ledger(
    session: Session, household_id: UUID, period: Period
) -> tuple[list[Balance], str]:
    expenses = erepo.ledger_expenses(session, household_id, period.id)
    shares = erepo.shares_for(session, household_id, [e.id for e in expenses])
    ledger = [
        LedgerExpense(
            payer_id=str(e.payer_member_id),
            amount_cents=e.amount_cents,
            shares=[Share(str(s.member_id), s.amount_cents) for s in shares.get(e.id, [])],
            personal=e.split_type == "personal",
        )
        for e in expenses
    ]
    balances = compute_balances(_member_order(session, household_id, period.seq), ledger)
    digest = hashlib.sha256(
        "|".join(sorted(f"{e.id}:{e.version}" for e in expenses)).encode()
    ).hexdigest()
    return balances, digest


def _balances_json(balances: Sequence[Balance]) -> list[dict[str, Any]]:
    return [
        {"member_id": b.id, "paid": b.paid_cents, "owed": b.owed_cents, "net": b.net_cents}
        for b in balances
    ]


def _supersede_current(session: Session, household_id: UUID, period: Period) -> int:
    """Supersede the current snapshot and cancel its pending transfers. Returns its seq."""
    current = erepo.current_snapshot(session, household_id, period.id)
    if current is None:
        latest = erepo.snapshots(session, household_id, period.id)
        return latest[-1].seq if latest else 0
    for t in erepo.snapshot_transfers(session, household_id, current.id, for_update=True):
        if t.status in ("sent", "confirmed", "disputed"):
            raise Conflict("Period is locked by a paid transfer", code="period_locked")
        if t.status == "pending":
            t.status = "cancelled"
            t.version += 1
    current.superseded_at = clock.now()
    return current.seq


def _mark_settled(session: Session, household_id: UUID, period: Period) -> None:
    period.status = "settled"
    period.settled_at = clock.now()
    period.version += 1
    # Leaving members whose last period is now settled are gone.
    for m in session.scalars(
        select(HouseholdMember).where(
            HouseholdMember.household_id == household_id,
            HouseholdMember.status == "leaving",
            HouseholdMember.left_period_seq <= period.seq,
        )
    ):
        open_or_closed = session.scalars(
            select(Period.id).where(
                Period.household_id == household_id,
                Period.seq <= period.seq,
                Period.seq >= m.joined_period_seq,
                Period.status != "settled",
                Period.id != period.id,
            )
        ).first()
        if open_or_closed is None:
            m.status = "left"


def write_snapshot(
    session: Session, household: Household, period: Period, trigger: str
) -> SettlementSnapshot:
    """Compute balances + greedy transfers and store them as a new current snapshot."""
    seq = _supersede_current(session, household.id, period) + 1
    balances, digest = compute_period_ledger(session, household.id, period)
    transfers = settle([NetEntry(b.id, b.net_cents) for b in balances])
    snapshot = SettlementSnapshot(
        household_id=household.id,
        period_id=period.id,
        seq=seq,
        trigger=trigger,
        balances=_balances_json(balances),
        transfers=[
            {"from_member_id": t.from_id, "to_member_id": t.to_id, "amount_cents": t.amount_cents}
            for t in transfers
        ],
        input_hash=digest,
    )
    session.add(snapshot)
    session.flush()
    for t in transfers:
        session.add(
            SettlementTransfer(
                household_id=household.id,
                period_id=period.id,
                snapshot_id=snapshot.id,
                from_member_id=UUID(t.from_id),
                to_member_id=UUID(t.to_id),
                amount_cents=t.amount_cents,
                status="pending",
            )
        )
    if transfers:
        if period.status == "settled":
            period.status = "closed"
            period.settled_at = None
    else:
        _mark_settled(session, household.id, period)
    session.flush()
    enqueue(
        session,
        "sync_period_tab",
        {"household_id": str(household.id), "period_id": str(period.id)},
        queue="sheets",
        queueing_lock=f"sheets:{period.id}",
    )
    return snapshot


def _close(
    session: Session, household: Household, period: Period, actor_user_id: UUID | None
) -> None:
    trigger = "reopen_close" if period.reopened_count > 0 else "close"
    period.status = "closed"
    period.closed_at = clock.now()
    period.closed_by = actor_user_id
    period.version += 1
    write_snapshot(session, household, period, trigger)
    enqueue(
        session,
        "notify_period_closed",
        {"household_id": str(household.id), "period_id": str(period.id)},
        queue="push",
    )


def after_edit_in_closed_period(session: Session, household: Household, period: Period) -> None:
    """Edit after close (unlocked): new snapshot, old pending transfers cancelled."""
    period.version += 1
    write_snapshot(session, household, period, "edit_after_close")


# ------------------------------------------------------------------ reads


def _household(session: Session, household_id: UUID) -> Household:
    household = hrepo.get_household(session, household_id)
    if household is None:
        raise NotFound("Household not found")
    return household


def _period_read(session: Session, household_id: UUID, period: Period) -> PeriodRead:
    expenses = [
        e
        for e in erepo.ledger_expenses(session, household_id, period.id)
        if e.split_type != "personal"
    ]
    by_cat: dict[UUID | None, int] = {}
    for e in expenses:
        by_cat[e.category_id] = by_cat.get(e.category_id, 0) + e.amount_cents
    return PeriodRead(
        id=period.id,
        seq=period.seq,
        status=period.status,
        started_at=period.started_at,
        closed_at=period.closed_at,
        settled_at=period.settled_at,
        reopened_count=period.reopened_count,
        version=period.version,
        total_cents=sum(e.amount_cents for e in expenses),
        totals_by_category=[
            {"category_id": str(k) if k else None, "total_cents": v} for k, v in by_cat.items()
        ],
        locked=period_state(session, period) == "locked",
    )


def load_period(
    session: Session, household_id: UUID, key: PeriodKey, *, for_update: bool = False
) -> Period:
    if key == "current":
        period = erepo.get_latest_period(session, household_id, for_update=for_update)
    else:
        period = erepo.get_period_by_seq(session, household_id, key, for_update=for_update)
    if period is None:
        raise NotFound("Period not found")
    return period


def list_periods(
    session: Session, actor: HouseholdActor, *, limit: int, before: int | None
) -> tuple[list[PeriodRead], str | None]:
    rows = erepo.list_periods(session, actor.household_id, limit=limit + 1, before_seq=before)
    items = [_period_read(session, actor.household_id, p) for p in rows[:limit]]
    next_cursor = str(rows[limit - 1].seq) if len(rows) > limit else None
    return items, next_cursor


def get_period(session: Session, actor: HouseholdActor, key: PeriodKey) -> PeriodRead:
    return _period_read(session, actor.household_id, load_period(session, actor.household_id, key))


def _snapshot_read(s: SettlementSnapshot) -> SnapshotRead:
    return SnapshotRead.model_validate(s)


def get_balance(session: Session, actor: HouseholdActor, key: PeriodKey) -> PeriodBalanceRead:
    household = _household(session, actor.household_id)
    period = load_period(session, household.id, key)
    balances, digest = compute_period_ledger(session, household.id, period)
    snapshot = erepo.current_snapshot(session, household.id, period.id)
    return PeriodBalanceRead(
        period=_period_read(session, household.id, period),
        balances=[
            BalanceRead(
                member_id=UUID(b.id),
                paid_cents=b.paid_cents,
                owed_cents=b.owed_cents,
                net_cents=b.net_cents,
            )
            for b in balances
        ],
        snapshot=_snapshot_read(snapshot) if snapshot else None,
        drift=snapshot is not None and snapshot.input_hash != digest,
    )


def get_settlement(session: Session, actor: HouseholdActor, key: PeriodKey) -> SettlementRead:
    household = _household(session, actor.household_id)
    period = load_period(session, household.id, key)
    all_snapshots = erepo.snapshots(session, household.id, period.id)
    current = next((s for s in reversed(all_snapshots) if s.superseded_at is None), None)
    transfers = (
        erepo.snapshot_transfers(session, household.id, current.id) if current is not None else []
    )
    return SettlementRead(
        period=_period_read(session, household.id, period),
        snapshot=_snapshot_read(current) if current else None,
        transfers=[TransferRead.model_validate(t) for t in transfers],
        previous_snapshots=[_snapshot_read(s) for s in all_snapshots if s is not current],
    )


# ----------------------------------------------------------- close/reopen


def close_period(
    session: Session, actor: HouseholdActor, key: PeriodKey, if_match: int | None
) -> PeriodRead:
    """Any active member closes the period. Idempotent on a closed/settled period."""
    require_active(actor)
    household = _household(session, actor.household_id)
    period = load_period(session, household.id, key, for_update=True)
    if period.status != "open":
        return _period_read(session, household.id, period)
    check_version(if_match, period.version, required=False)
    _close(session, household, period, actor.user_id)
    audit(
        session,
        household_id=household.id,
        entity="period",
        entity_id=period.id,
        actor_user_id=actor.user_id,
        action="close",
        diff={"seq": period.seq},
    )
    session.commit()
    return _period_read(session, household.id, period)


def start_period(session: Session, actor: HouseholdActor) -> PeriodRead:
    """Any active member starts the next period once the latest one is closed."""
    require_active(actor)
    # Lock the household row so two members starting at once cannot both succeed.
    household = hrepo.get_household(session, actor.household_id, for_update=True)
    if household is None:
        raise NotFound("Household not found")
    latest = erepo.get_latest_period(session, household.id)
    if latest is not None and latest.status == "open":
        raise Conflict(
            "Close the current period before starting a new one",
            code="period_open",
            extra={"seq": latest.seq},
        )
    period = Period(
        household_id=household.id,
        seq=(latest.seq if latest else 0) + 1,
        status="open",
        started_at=clock.now(),
    )
    session.add(period)
    session.flush()
    audit(
        session,
        household_id=household.id,
        entity="period",
        entity_id=period.id,
        actor_user_id=actor.user_id,
        action="start",
        diff={"seq": period.seq},
    )
    session.commit()
    log.info("period_started", household_id=str(household.id), seq=period.seq)
    return _period_read(session, household.id, period)


def reopen_period(
    session: Session, actor: HouseholdActor, key: PeriodKey, data: ReopenIn
) -> PeriodRead:
    """Admin reopens the latest period while nobody has paid it yet."""
    require_admin(actor)
    household = _household(session, actor.household_id)
    period = load_period(session, household.id, key, for_update=True)
    if period.status == "open":
        raise Conflict("Period is already open", code="period_state_changed")
    latest = erepo.get_latest_period(session, household.id)
    if latest is not None and latest.id != period.id:
        raise Conflict("Only the latest period can be reopened", code="period_not_latest")
    if period_state(session, period) == "locked":
        raise Conflict(
            "Period has sent or confirmed transfers and cannot be reopened", code="period_locked"
        )
    _supersede_current(session, household.id, period)
    period.status = "open"
    period.closed_at = None
    period.closed_by = None
    period.settled_at = None
    period.reopened_count += 1
    period.version += 1
    audit(
        session,
        household_id=household.id,
        entity="period",
        entity_id=period.id,
        actor_user_id=actor.user_id,
        action="reopen",
        diff={"reason": data.reason},
    )
    session.commit()
    return _period_read(session, household.id, period)


# -------------------------------------------------------------- transfers


def _transfer_for_action(
    session: Session, actor: HouseholdActor, transfer_id: UUID
) -> SettlementTransfer:
    require_active(actor)
    transfer = erepo.get_transfer(session, actor.household_id, transfer_id, for_update=True)
    if transfer is None:
        raise NotFound("Transfer not found")
    if transfer.status == "cancelled":
        raise Conflict("Transfer was cancelled by a newer settlement", code="invalid_transition")
    return transfer


def _invalid(transfer: SettlementTransfer, action: str) -> Conflict:
    return Conflict(
        f"Cannot {action} a transfer in status {transfer.status}", code="invalid_transition"
    )


def mark_transfer_sent(
    session: Session, actor: HouseholdActor, transfer_id: UUID, data: TransferSentIn
) -> TransferRead:
    transfer = _transfer_for_action(session, actor, transfer_id)
    if transfer.from_member_id != actor.member_id:
        raise Forbidden("Only the debtor can mark a transfer as sent")
    if transfer.status not in ("pending", "disputed"):
        raise _invalid(transfer, "send")
    transfer.status = "sent"
    transfer.sent_at = clock.now()
    if data.note is not None:
        transfer.note = data.note
    transfer.version += 1
    session.commit()
    return TransferRead.model_validate(transfer)


def confirm_transfer(
    session: Session, actor: HouseholdActor, transfer_id: UUID, data: TransferConfirmIn
) -> TransferRead:
    transfer = _transfer_for_action(session, actor, transfer_id)
    if transfer.to_member_id != actor.member_id:
        creditor = hrepo.get_member(session, actor.household_id, transfer.to_member_id)
        creditor_left = creditor is not None and creditor.status == "left"
        if not (actor.is_admin and creditor_left):
            raise Forbidden("Only the creditor can confirm a transfer")
        if not data.note:
            raise Unprocessable("A note is required when an admin confirms for a former member")
    if transfer.status not in ("pending", "sent", "disputed"):
        raise _invalid(transfer, "confirm")
    transfer.status = "confirmed"
    transfer.confirmed_at = clock.now()
    transfer.confirmed_by = actor.user_id
    if data.note is not None:
        transfer.note = data.note
    transfer.version += 1
    session.flush()

    period = erepo.get_period(session, actor.household_id, transfer.period_id, for_update=True)
    assert period is not None
    remaining = [
        t
        for t in erepo.snapshot_transfers(session, actor.household_id, transfer.snapshot_id)
        if t.status != "confirmed"
    ]
    if not remaining and period.status == "closed":
        _mark_settled(session, actor.household_id, period)
    session.commit()
    return TransferRead.model_validate(transfer)


def dispute_transfer(
    session: Session, actor: HouseholdActor, transfer_id: UUID, data: TransferDisputeIn
) -> TransferRead:
    transfer = _transfer_for_action(session, actor, transfer_id)
    if transfer.to_member_id != actor.member_id:
        raise Forbidden("Only the creditor can dispute a transfer")
    if transfer.status != "sent":
        raise _invalid(transfer, "dispute")
    transfer.status = "disputed"
    transfer.note = data.note
    transfer.version += 1
    session.commit()
    return TransferRead.model_validate(transfer)


__all__ = [
    "after_edit_in_closed_period",
    "close_period",
    "compute_period_ledger",
    "confirm_transfer",
    "create_first_period",
    "dispute_transfer",
    "get_balance",
    "get_period",
    "get_settlement",
    "list_periods",
    "load_period",
    "mark_transfer_sent",
    "period_state",
    "reopen_period",
    "require_open_period",
    "start_period",
    "write_snapshot",
]
