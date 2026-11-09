"""Household-scoped expense, period and settlement queries."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from split_ranch.models import (
    Expense,
    ExpenseRevision,
    ExpenseShare,
    Period,
    SettlementSnapshot,
    SettlementTransfer,
)


def get_expense(
    session: Session, household_id: UUID, expense_id: UUID, *, for_update: bool = False
) -> Expense | None:
    stmt = select(Expense).where(Expense.household_id == household_id, Expense.id == expense_id)
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def expense_exists_anywhere(session: Session, expense_id: UUID) -> bool:
    """Used only to reject client-supplied id collisions across tenants."""
    return session.scalars(select(Expense.id).where(Expense.id == expense_id)).first() is not None


def shares_for(
    session: Session, household_id: UUID, expense_ids: Sequence[UUID]
) -> dict[UUID, list[ExpenseShare]]:
    out: dict[UUID, list[ExpenseShare]] = defaultdict(list)
    if not expense_ids:
        return out
    rows = session.scalars(
        select(ExpenseShare)
        .where(ExpenseShare.household_id == household_id, ExpenseShare.expense_id.in_(expense_ids))
        .order_by(ExpenseShare.expense_id, ExpenseShare.sort_key)
    ).all()
    for s in rows:
        out[s.expense_id].append(s)
    return out


def list_expenses(
    session: Session,
    household_id: UUID,
    *,
    viewer_user_id: UUID,
    limit: int,
    after: tuple[date, UUID] | None = None,
    period_id: UUID | None = None,
    category_id: UUID | None = None,
    payer_member_id: UUID | None = None,
    q: str | None = None,
    status: str | None = None,
) -> Sequence[Expense]:
    """Keyset pagination on (expense_date DESC, id DESC). Drafts only for their creator."""
    stmt = select(Expense).where(Expense.household_id == household_id, Expense.deleted_at.is_(None))
    if status == "draft":
        stmt = stmt.where(Expense.status == "draft", Expense.created_by_user_id == viewer_user_id)
    elif status == "confirmed":
        stmt = stmt.where(Expense.status == "confirmed")
    else:
        stmt = stmt.where(
            or_(
                Expense.status == "confirmed",
                and_(Expense.status == "draft", Expense.created_by_user_id == viewer_user_id),
            )
        )
    if period_id is not None:
        stmt = stmt.where(Expense.period_id == period_id)
    if category_id is not None:
        stmt = stmt.where(Expense.category_id == category_id)
    if payer_member_id is not None:
        stmt = stmt.where(Expense.payer_member_id == payer_member_id)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Expense.description.ilike(f"%{escaped}%", escape="\\"))
    if after is not None:
        d, i = after
        stmt = stmt.where(
            or_(Expense.expense_date < d, and_(Expense.expense_date == d, Expense.id < i))
        )
    stmt = stmt.order_by(Expense.expense_date.desc(), Expense.id.desc()).limit(limit)
    return session.scalars(stmt).all()


def ledger_expenses(session: Session, household_id: UUID, period_id: UUID) -> Sequence[Expense]:
    """Confirmed, non-deleted expenses of a period (personal ones included; filtered later)."""
    return session.scalars(
        select(Expense)
        .where(
            Expense.household_id == household_id,
            Expense.period_id == period_id,
            Expense.deleted_at.is_(None),
            Expense.status == "confirmed",
        )
        .order_by(Expense.created_at, Expense.id)
    ).all()


def open_period_expenses(
    session: Session, household_id: UUID, *, split_origin: str | None = None
) -> Sequence[Expense]:
    stmt = (
        select(Expense)
        .join(Period, and_(Period.id == Expense.period_id, Period.household_id == household_id))
        .where(
            Expense.household_id == household_id,
            Expense.deleted_at.is_(None),
            Period.status == "open",
        )
        .order_by(Expense.created_at)
        .with_for_update(of=Expense)
    )
    if split_origin is not None:
        stmt = stmt.where(Expense.split_origin == split_origin)
    return session.scalars(stmt).all()


def revisions(session: Session, household_id: UUID, expense_id: UUID) -> Sequence[ExpenseRevision]:
    return session.scalars(
        select(ExpenseRevision)
        .where(
            ExpenseRevision.household_id == household_id, ExpenseRevision.expense_id == expense_id
        )
        .order_by(ExpenseRevision.version)
    ).all()


# ---------------------------------------------------------------- periods


def get_period_by_seq(
    session: Session, household_id: UUID, seq: int, *, for_update: bool = False
) -> Period | None:
    stmt = select(Period).where(Period.household_id == household_id, Period.seq == seq)
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def get_latest_period(
    session: Session, household_id: UUID, *, for_update: bool = False
) -> Period | None:
    """The most recently started period (the open one, if any: only the latest can be open)."""
    stmt = (
        select(Period)
        .where(Period.household_id == household_id)
        .order_by(Period.seq.desc())
        .limit(1)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def get_open_period(
    session: Session, household_id: UUID, *, for_update: bool = False
) -> Period | None:
    stmt = select(Period).where(Period.household_id == household_id, Period.status == "open")
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def get_period(
    session: Session, household_id: UUID, period_id: UUID, *, for_update: bool = False
) -> Period | None:
    stmt = select(Period).where(Period.household_id == household_id, Period.id == period_id)
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def list_periods(
    session: Session, household_id: UUID, *, limit: int, before_seq: int | None = None
) -> Sequence[Period]:
    stmt = select(Period).where(Period.household_id == household_id)
    if before_seq is not None:
        stmt = stmt.where(Period.seq < before_seq)
    return session.scalars(stmt.order_by(Period.seq.desc()).limit(limit)).all()


def current_snapshot(
    session: Session, household_id: UUID, period_id: UUID
) -> SettlementSnapshot | None:
    return session.scalars(
        select(SettlementSnapshot)
        .where(
            SettlementSnapshot.household_id == household_id,
            SettlementSnapshot.period_id == period_id,
            SettlementSnapshot.superseded_at.is_(None),
        )
        .order_by(SettlementSnapshot.seq.desc())
    ).first()


def snapshots(
    session: Session, household_id: UUID, period_id: UUID
) -> Sequence[SettlementSnapshot]:
    return session.scalars(
        select(SettlementSnapshot)
        .where(
            SettlementSnapshot.household_id == household_id,
            SettlementSnapshot.period_id == period_id,
        )
        .order_by(SettlementSnapshot.seq)
    ).all()


def snapshot_transfers(
    session: Session, household_id: UUID, snapshot_id: UUID, *, for_update: bool = False
) -> Sequence[SettlementTransfer]:
    stmt = (
        select(SettlementTransfer)
        .where(
            SettlementTransfer.household_id == household_id,
            SettlementTransfer.snapshot_id == snapshot_id,
        )
        .order_by(SettlementTransfer.created_at, SettlementTransfer.id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).all()


def period_has_locking_transfer(session: Session, household_id: UUID, period_id: UUID) -> bool:
    """A period is locked once any transfer was sent or confirmed (disputed implies sent)."""
    return (
        session.scalars(
            select(SettlementTransfer.id).where(
                SettlementTransfer.household_id == household_id,
                SettlementTransfer.period_id == period_id,
                SettlementTransfer.status.in_(("sent", "confirmed", "disputed")),
            )
        ).first()
        is not None
    )


def get_transfer(
    session: Session, household_id: UUID, transfer_id: UUID, *, for_update: bool = False
) -> SettlementTransfer | None:
    stmt = select(SettlementTransfer).where(
        SettlementTransfer.household_id == household_id, SettlementTransfer.id == transfer_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()
