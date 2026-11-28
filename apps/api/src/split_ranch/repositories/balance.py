"""Per-member totals for the group balance, aggregated in the database.

The group has no periods, so its ledger grows forever: summing in SQL returns one row per
member instead of every live expense, share and payment.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, func, literal, select, union_all
from sqlalchemy.orm import Session

from split_ranch.models import Expense, ExpenseShare, Payment


def paid_and_owed(session: Session, group_id: UUID) -> dict[UUID, tuple[int, int]]:
    """(paid, owed) cents per member over live non-personal expenses and confirmed payments.

    A confirmed payment from D to C counts as paid by D and owed by C (see
    `use_cases.balance`). Members that appear nowhere are missing from the result.
    """
    zero = literal(0)
    counted = and_(
        Expense.group_id == group_id,
        Expense.deleted_at.is_(None),
        Expense.split_type != "personal",
    )
    confirmed = and_(Payment.group_id == group_id, Payment.status == "confirmed")
    entries = union_all(
        select(
            Expense.payer_member_id.label("member_id"),
            Expense.amount_cents.label("paid"),
            zero.label("owed"),
        ).where(counted),
        select(ExpenseShare.member_id, zero, ExpenseShare.amount_cents)
        .join(
            Expense,
            and_(Expense.id == ExpenseShare.expense_id, Expense.group_id == ExpenseShare.group_id),
        )
        .where(ExpenseShare.group_id == group_id, counted),
        select(Payment.from_member_id, Payment.amount_cents, zero).where(confirmed),
        select(Payment.to_member_id, zero, Payment.amount_cents).where(confirmed),
    ).subquery()
    rows = session.execute(
        select(entries.c.member_id, func.sum(entries.c.paid), func.sum(entries.c.owed)).group_by(
            entries.c.member_id
        )
    ).all()
    return {member_id: (int(paid), int(owed)) for member_id, paid, owed in rows}
