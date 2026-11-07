"""Pure domain: money, split and settlement. No I/O, no frameworks.

Mirrors `packages/domain` (TypeScript) 1:1; parity is enforced by `packages/domain-vectors`.
"""

from split_ranch.domain.errors import DomainError, DomainErrorCode
from split_ranch.domain.money import MAX_AMOUNT_CENTS, allocate
from split_ranch.domain.settle import (
    Balance,
    LedgerExpense,
    NetEntry,
    Transfer,
    compute_balances,
    settle,
)
from split_ranch.domain.split import (
    BASIS_POINTS_TOTAL,
    SPLIT_TYPES,
    Share,
    SplitParticipant,
    SplitType,
    resolve_shares,
)

__all__ = [
    "BASIS_POINTS_TOTAL",
    "MAX_AMOUNT_CENTS",
    "SPLIT_TYPES",
    "Balance",
    "DomainError",
    "DomainErrorCode",
    "LedgerExpense",
    "NetEntry",
    "Share",
    "SplitParticipant",
    "SplitType",
    "Transfer",
    "allocate",
    "compute_balances",
    "resolve_shares",
    "settle",
]
