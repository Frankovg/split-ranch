"""Group-scoped expense queries."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from split_ranch.models import Expense, ExpenseShare, History


@dataclass(frozen=True)
class ExpenseFilters:
    """Filters shared by the expense list and the summary (inclusive dates)."""

    date_from: date | None = None
    date_to: date | None = None
    category_id: UUID | None = None
    payer_member_id: UUID | None = None
    created_by_user_id: UUID | None = None
    q: str | None = None


def _filtered(stmt: Select[Any], group_id: UUID, f: ExpenseFilters) -> Select[Any]:
    stmt = stmt.where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
    if f.date_from is not None:
        stmt = stmt.where(Expense.expense_date >= f.date_from)
    if f.date_to is not None:
        stmt = stmt.where(Expense.expense_date <= f.date_to)
    if f.category_id is not None:
        stmt = stmt.where(Expense.category_id == f.category_id)
    if f.payer_member_id is not None:
        stmt = stmt.where(Expense.payer_member_id == f.payer_member_id)
    if f.created_by_user_id is not None:
        stmt = stmt.where(Expense.created_by_user_id == f.created_by_user_id)
    if f.q:
        escaped = f.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Expense.description.ilike(f"%{escaped}%", escape="\\"))
    return stmt


def get_expense(
    session: Session, group_id: UUID, expense_id: UUID, *, for_update: bool = False
) -> Expense | None:
    stmt = select(Expense).where(Expense.group_id == group_id, Expense.id == expense_id)
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def shares_for(
    session: Session, group_id: UUID, expense_ids: Sequence[UUID]
) -> dict[UUID, list[ExpenseShare]]:
    out: dict[UUID, list[ExpenseShare]] = defaultdict(list)
    if not expense_ids:
        return out
    rows = session.scalars(
        select(ExpenseShare)
        .where(ExpenseShare.group_id == group_id, ExpenseShare.expense_id.in_(expense_ids))
        .order_by(ExpenseShare.expense_id, ExpenseShare.sort_key)
    ).all()
    for s in rows:
        out[s.expense_id].append(s)
    return out


def list_expenses(
    session: Session,
    group_id: UUID,
    filters: ExpenseFilters,
    *,
    limit: int,
    after: tuple[date, UUID] | None = None,
) -> Sequence[Expense]:
    """Keyset pagination on (expense_date DESC, id DESC)."""
    stmt = _filtered(select(Expense), group_id, filters)
    if after is not None:
        d, i = after
        stmt = stmt.where(
            or_(Expense.expense_date < d, and_(Expense.expense_date == d, Expense.id < i))
        )
    stmt = stmt.order_by(Expense.expense_date.desc(), Expense.id.desc()).limit(limit)
    return session.scalars(stmt).all()


@dataclass(frozen=True)
class SummaryRows:
    count: int
    total_cents: int
    by_category: list[tuple[UUID | None, int]]
    by_payer: list[tuple[UUID, int]]


def summary(
    session: Session,
    group_id: UUID,
    filters: ExpenseFilters,
    *,
    share_member_id: UUID | None = None,
) -> SummaryRows:
    """Totals of the live expenses matching `filters`.

    Without `share_member_id`: full amounts of the shared (non-personal) expenses.
    With it: only that member's share of each expense they take part in, personal
    expenses included (a personal expense's single share is the whole amount).
    """
    if share_member_id is None:
        amount = func.coalesce(func.sum(Expense.amount_cents), 0)

        def base(*cols: Any) -> Select[Any]:
            return _filtered(select(*cols), group_id, filters).where(
                Expense.split_type != "personal"
            )

    else:
        amount = func.coalesce(func.sum(ExpenseShare.amount_cents), 0)

        def base(*cols: Any) -> Select[Any]:
            stmt = (
                select(*cols)
                .select_from(Expense)
                .join(
                    ExpenseShare,
                    and_(
                        ExpenseShare.expense_id == Expense.id,
                        ExpenseShare.group_id == Expense.group_id,
                        ExpenseShare.member_id == share_member_id,
                    ),
                )
            )
            return _filtered(stmt, group_id, filters)

    count, total = session.execute(base(func.count(), amount)).one()
    by_category = session.execute(
        base(Expense.category_id, amount)
        .group_by(Expense.category_id)
        .order_by(amount.desc(), Expense.category_id)
    ).all()
    by_payer = session.execute(
        base(Expense.payer_member_id, amount)
        .group_by(Expense.payer_member_id)
        .order_by(amount.desc(), Expense.payer_member_id)
    ).all()
    return SummaryRows(
        count=int(count),
        total_cents=int(total),
        by_category=[(c, int(t)) for c, t in by_category],
        by_payer=[(p, int(t)) for p, t in by_payer],
    )


def live_expenses(session: Session, group_id: UUID) -> Sequence[Expense]:
    """Every non-deleted expense of the group (personal ones included; filtered later)."""
    return session.scalars(
        select(Expense)
        .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
        .order_by(Expense.created_at, Expense.id)
    ).all()


def all_shares(session: Session, group_id: UUID) -> dict[UUID, list[ExpenseShare]]:
    """Shares of every live expense of the group, keyed by expense id."""
    out: dict[UUID, list[ExpenseShare]] = defaultdict(list)
    rows = session.scalars(
        select(ExpenseShare)
        .join(
            Expense,
            and_(Expense.id == ExpenseShare.expense_id, Expense.group_id == ExpenseShare.group_id),
        )
        .where(ExpenseShare.group_id == group_id, Expense.deleted_at.is_(None))
        .order_by(ExpenseShare.expense_id, ExpenseShare.sort_key)
    ).all()
    for s in rows:
        out[s.expense_id].append(s)
    return out


def member_has_live_expenses(session: Session, group_id: UUID, member_id: UUID) -> bool:
    """Whether a member pays or takes part in any live expense of the group."""
    paid = select(Expense.id).where(
        Expense.group_id == group_id,
        Expense.deleted_at.is_(None),
        Expense.payer_member_id == member_id,
    )
    shared = (
        select(ExpenseShare.expense_id)
        .join(
            Expense,
            and_(Expense.id == ExpenseShare.expense_id, Expense.group_id == ExpenseShare.group_id),
        )
        .where(
            ExpenseShare.group_id == group_id,
            ExpenseShare.member_id == member_id,
            Expense.deleted_at.is_(None),
        )
    )
    return bool(session.scalar(select(paid.exists())) or session.scalar(select(shared.exists())))


def revisions(session: Session, group_id: UUID, expense_id: UUID) -> Sequence[History]:
    return session.scalars(
        select(History)
        .where(
            History.group_id == group_id,
            History.entity == "expense",
            History.entity_id == expense_id,
        )
        .order_by(History.version)
    ).all()
