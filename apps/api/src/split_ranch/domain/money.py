"""Money helpers. All amounts are integer cents."""

from collections.abc import Sequence

from split_ranch.domain.errors import DomainError

# Upper bound for a single amount: 1,000,000.00 EUR in cents.
MAX_AMOUNT_CENTS = 100_000_000

# Same bound as JavaScript's Number.MAX_SAFE_INTEGER, kept for parity with the TS domain.
MAX_SAFE_INTEGER = 2**53 - 1


def is_safe_int(value: object) -> bool:
    """True for real ints (not bools) within the JS safe-integer range."""
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER
    )


def allocate(total: int, ratios: Sequence[int]) -> list[int]:
    """Split `total` cents proportionally to integer `ratios` without losing cents.

    Largest remainder (Hamilton) method: every share is floored, then the leftover cents
    go to the shares with the largest fractional remainder; ties are broken by input
    position (earlier wins). Negative totals are allocated symmetrically.
    Must stay equivalent to `allocate` in packages/domain/src/money.ts.
    """
    if not is_safe_int(total):
        raise DomainError("invalid_amount", f"total must be a safe integer, got {total!r}")
    if len(ratios) == 0 or any(not is_safe_int(r) or r < 0 for r in ratios):
        raise DomainError("invalid_ratios", "ratios must be non-negative integers")
    if all(r == 0 for r in ratios):
        raise DomainError("invalid_ratios", "at least one ratio must be positive")
    if total < 0:
        return [-x for x in allocate(-total, ratios)]

    r_sum = sum(ratios)
    base = [total * r // r_sum for r in ratios]
    frac = [total * r % r_sum for r in ratios]
    leftover = total - sum(base)
    order = sorted(range(len(ratios)), key=lambda i: (-frac[i], i))
    for i in order[:leftover]:
        base[i] += 1
    return base
