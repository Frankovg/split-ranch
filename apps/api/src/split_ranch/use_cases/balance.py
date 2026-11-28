"""The group's running balance: every live expense plus every confirmed payment.

A confirmed payment from D to C of `x` counts as an expense paid by D whose only share is
owed by C: D's net rises by `x` and C's falls by `x`. The paid and owed totals are summed
in SQL (`repositories.balance`); the result equals the domain's `compute_balances` over
the same rows (the DB triggers already guarantee each expense's shares sum to its amount),
and the transfers come from the domain's `settle`, in parity with the TS one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from split_ranch.core.actor import GroupActor
from split_ranch.domain import Balance, NetEntry, settle
from split_ranch.models import Payment
from split_ranch.repositories import balance as brepo
from split_ranch.repositories import groups as grepo
from split_ranch.repositories import payments as prepo
from split_ranch.schemas.payments import BalanceRead, GroupBalanceRead, SuggestionRead


@dataclass(frozen=True)
class GroupBalance:
    balances: list[Balance]
    pending: Sequence[Payment]
    # Suggestions computed after counting the payments already sent (not yet confirmed),
    # so nobody is told to pay twice.
    suggestions: list[tuple[str, str, int]]


def _balances(session: Session, group_id: UUID) -> list[Balance]:
    """Every member in canonical order (zeros included), like `compute_balances`."""
    totals = brepo.paid_and_owed(session, group_id)
    order = [m.id for m in grepo.list_members(session, group_id)]
    # Shares and payments reference members of the same group (composite FKs), so this
    # only matters if that ever changes: keep their totals instead of dropping them.
    order += sorted(set(totals) - set(order))
    out: list[Balance] = []
    for member_id in order:
        paid, owed = totals.get(member_id, (0, 0))
        out.append(Balance(str(member_id), paid, owed, paid - owed))
    return out


def compute_group_balance(session: Session, group_id: UUID) -> GroupBalance:
    balances = _balances(session, group_id)
    pending = prepo.payments_with_status(session, group_id, ["sent"])
    projected = {b.id: b.net_cents for b in balances}
    for p in pending:
        projected[str(p.from_member_id)] += p.amount_cents
        projected[str(p.to_member_id)] -= p.amount_cents
    transfers = settle([NetEntry(member_id, net) for member_id, net in projected.items()])
    return GroupBalance(
        balances=balances,
        pending=pending,
        suggestions=[(t.from_id, t.to_id, t.amount_cents) for t in transfers],
    )


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
