"""Split engine: resolve how much each participant owes for one expense."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from split_ranch.domain.errors import DomainError
from split_ranch.domain.money import allocate, is_safe_int

SplitType = Literal["equal", "weights", "percentages", "exact", "single", "personal"]

SPLIT_TYPES: tuple[SplitType, ...] = (
    "equal",
    "weights",
    "percentages",
    "exact",
    "single",
    "personal",
)

BASIS_POINTS_TOTAL = 10_000


@dataclass(frozen=True, slots=True)
class SplitParticipant:
    """A participant of a split, in canonical order (sort_key ASC, id ASC)."""

    id: str
    weight: int | None = None
    basis_points: int | None = None
    exact_cents: int | None = None


@dataclass(frozen=True, slots=True)
class Share:
    id: str
    amount_cents: int


def _require_int_field(value: int | None, participant_id: str, field: str, minimum: int) -> int:
    if value is None or not is_safe_int(value) or value < minimum:
        raise DomainError(
            "invalid_split",
            f"participant {participant_id}: {field} must be an integer >= {minimum}",
        )
    return value


def resolve_shares(
    amount_cents: int,
    payer_id: str,
    split_type: SplitType,
    participants: Sequence[SplitParticipant],
) -> list[Share]:
    """Resolve the shares of one expense. Returned amounts always sum to `amount_cents`.

    `personal` ignores participants (the payer owes everything); `single` needs exactly
    one participant. Mirrors `resolveShares` in packages/domain/src/split.ts.
    """
    if not is_safe_int(amount_cents) or amount_cents == 0:
        raise DomainError("invalid_amount", "amount must be a non-zero integer")

    if split_type == "personal":
        return [Share(payer_id, amount_cents)]

    if len(participants) == 0:
        raise DomainError("invalid_split", "at least one participant is required")
    if len({p.id for p in participants}) != len(participants):
        raise DomainError("invalid_split", "duplicate participant")

    amounts: list[int]
    if split_type == "equal":
        amounts = allocate(amount_cents, [1] * len(participants))
    elif split_type == "weights":
        weights = [_require_int_field(p.weight, p.id, "weight", 0) for p in participants]
        amounts = allocate(amount_cents, weights)
    elif split_type == "percentages":
        bps = [_require_int_field(p.basis_points, p.id, "basis_points", 0) for p in participants]
        total_bps = sum(bps)
        if total_bps != BASIS_POINTS_TOTAL:
            raise DomainError(
                "split_mismatch",
                f"basis points must sum to {BASIS_POINTS_TOTAL}, got {total_bps}",
            )
        amounts = allocate(amount_cents, bps)
    elif split_type == "exact":
        exact: list[int] = []
        for p in participants:
            if p.exact_cents is None or not is_safe_int(p.exact_cents):
                raise DomainError(
                    "invalid_split", f"participant {p.id}: exact_cents must be an integer"
                )
            exact.append(p.exact_cents)
        total_exact = sum(exact)
        if total_exact != amount_cents:
            raise DomainError(
                "split_mismatch",
                f"exact amounts sum to {total_exact}, expected {amount_cents}",
            )
        amounts = exact
    elif split_type == "single":
        if len(participants) != 1:
            raise DomainError("invalid_split", "single split needs exactly one participant")
        amounts = [amount_cents]
    else:
        raise DomainError("invalid_split", f"unknown split type {split_type!s}")

    return [Share(p.id, a) for p, a in zip(participants, amounts, strict=True)]
