"""The group's running balance: every live expense plus every confirmed payment.

A confirmed payment from D to C of `x` enters the ledger as an expense paid by D whose only
share is owed by C: D's net rises by `x` and C's falls by `x`, so the domain's
`compute_balances` and `settle` are reused unchanged (and stay in parity with the TS ones).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from split_ranch.core.actor import GroupActor
from split_ranch.domain import Balance, LedgerExpense, NetEntry, Share, compute_balances, settle
from split_ranch.models import Payment
from split_ranch.repositories import expenses as erepo
from split_ranch.repositories import groups as grepo
from split_ranch.repositories import payments as prepo
from split_ranch.schemas.payments import BalanceRead, GroupBalanceRead, SuggestionRead


def _payment_row(p: Payment) -> LedgerExpense:
    return LedgerExpense(
        payer_id=str(p.from_member_id),
        amount_cents=p.amount_cents,
        shares=[Share(str(p.to_member_id), p.amount_cents)],
    )


def _expense_rows(session: Session, group_id: UUID) -> list[LedgerExpense]:
    expenses = erepo.live_expenses(session, group_id)
    shares = erepo.all_shares(session, group_id)
    return [
        LedgerExpense(
            payer_id=str(e.payer_member_id),
            amount_cents=e.amount_cents,
            shares=[Share(str(s.member_id), s.amount_cents) for s in shares.get(e.id, [])],
            personal=e.split_type == "personal",
        )
        for e in expenses
    ]


@dataclass(frozen=True)
class GroupBalance:
    balances: list[Balance]
    pending: Sequence[Payment]
    # Suggestions computed after counting the payments already sent (not yet confirmed),
    # so nobody is told to pay twice.
    suggestions: list[tuple[str, str, int]]


def compute_group_balance(session: Session, group_id: UUID) -> GroupBalance:
    order = [str(m.id) for m in grepo.list_members(session, group_id)]
    rows = _expense_rows(session, group_id)
    rows += [_payment_row(p) for p in prepo.payments_with_status(session, group_id, ["confirmed"])]
    balances = compute_balances(order, rows)
    pending = prepo.payments_with_status(session, group_id, ["sent"])
    projected = compute_balances(order, rows + [_payment_row(p) for p in pending])
    transfers = settle([NetEntry(b.id, b.net_cents) for b in projected])
    return GroupBalance(
        balances=balances,
        pending=pending,
        suggestions=[(t.from_id, t.to_id, t.amount_cents) for t in transfers],
    )


def member_net(session: Session, group_id: UUID, member_id: UUID) -> int:
    """The member's confirmed net (0 when they appear nowhere)."""
    for b in compute_group_balance(session, group_id).balances:
        if b.id == str(member_id):
            return b.net_cents
    return 0


def get_balance(session: Session, actor: GroupActor) -> GroupBalanceRead:
    result = compute_group_balance(session, actor.group_id)
    pending_out: dict[str, int] = {}
    pending_in: dict[str, int] = {}
    for p in result.pending:
        pending_out[str(p.from_member_id)] = pending_out.get(str(p.from_member_id), 0) + (
            p.amount_cents
        )
        pending_in[str(p.to_member_id)] = pending_in.get(str(p.to_member_id), 0) + p.amount_cents
    return GroupBalanceRead(
        balances=[
            BalanceRead(
                member_id=UUID(b.id),
                paid_cents=b.paid_cents,
                owed_cents=b.owed_cents,
                net_cents=b.net_cents,
                pending_out_cents=pending_out.get(b.id, 0),
                pending_in_cents=pending_in.get(b.id, 0),
            )
            for b in result.balances
        ],
        suggestions=[
            SuggestionRead(from_member_id=UUID(f), to_member_id=UUID(t), amount_cents=a)
            for f, t, a in result.suggestions
        ],
    )
