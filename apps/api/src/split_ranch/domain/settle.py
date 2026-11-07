"""Balances and deterministic greedy settlement."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from split_ranch.domain.errors import DomainError
from split_ranch.domain.split import Share


@dataclass(frozen=True, slots=True)
class LedgerExpense:
    payer_id: str
    amount_cents: int
    shares: Sequence[Share] = field(default_factory=tuple)
    # Personal expenses are excluded from balances and settlement.
    personal: bool = False


@dataclass(frozen=True, slots=True)
class Balance:
    id: str
    paid_cents: int
    owed_cents: int
    net_cents: int


@dataclass(frozen=True, slots=True)
class NetEntry:
    id: str
    net_cents: int


@dataclass(frozen=True, slots=True)
class Transfer:
    from_id: str
    to_id: str
    amount_cents: int


def compute_balances(
    member_order: Sequence[str], expenses: Sequence[LedgerExpense]
) -> list[Balance]:
    """Compute paid / owed / net per member.

    `member_order` is the canonical order and defines the output order; ids found in
    expenses but not in `member_order` are appended in order of first appearance.
    Mirrors `computeBalances` in packages/domain/src/settle.ts.
    """
    order: list[str] = []
    paid: dict[str, int] = {}
    owed: dict[str, int] = {}

    def touch(member_id: str) -> None:
        if member_id not in paid:
            paid[member_id] = 0
            owed[member_id] = 0
            order.append(member_id)

    for member_id in member_order:
        touch(member_id)

    for e in expenses:
        if e.personal:
            continue
        shares_sum = sum(s.amount_cents for s in e.shares)
        if shares_sum != e.amount_cents:
            raise DomainError(
                "split_mismatch", f"shares sum {shares_sum} != amount {e.amount_cents}"
            )
        touch(e.payer_id)
        paid[e.payer_id] += e.amount_cents
        for s in e.shares:
            touch(s.id)
            owed[s.id] += s.amount_cents

    return [Balance(i, paid[i], owed[i], paid[i] - owed[i]) for i in order]


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def settle(nets: Sequence[NetEntry]) -> list[Transfer]:
    """Deterministic greedy settlement.

    Repeatedly match the largest creditor with the largest debtor (ties -> earlier in
    input order). At most n-1 transfers, no cent lost. Mirrors `settle` in
    packages/domain/src/settle.ts.
    """
    total = sum(n.net_cents for n in nets)
    if total != 0:
        raise DomainError("unbalanced_nets", f"nets must sum to 0, got {total}")

    ids = [n.id for n in nets]
    remaining = [n.net_cents for n in nets]
    transfers: list[Transfer] = []

    def pick(sign: int) -> int | None:
        best: int | None = None
        for i, value in enumerate(remaining):
            if _sign(value) != sign:
                continue
            if best is None or abs(value) > abs(remaining[best]):
                best = i
        return best

    while True:
        creditor = pick(1)
        debtor = pick(-1)
        if creditor is None or debtor is None:
            break
        amount = min(remaining[creditor], -remaining[debtor])
        transfers.append(Transfer(ids[debtor], ids[creditor], amount))
        remaining[creditor] -= amount
        remaining[debtor] += amount
    return transfers
