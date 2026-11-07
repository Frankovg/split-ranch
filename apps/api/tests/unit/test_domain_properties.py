"""Hypothesis property tests for the pure domain (see docs/09)."""

from __future__ import annotations

import random
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from split_ranch.domain import (
    DomainError,
    LedgerExpense,
    NetEntry,
    SplitParticipant,
    allocate,
    compute_balances,
    resolve_shares,
    settle,
)

ratios_st = st.lists(st.integers(min_value=0, max_value=10_000), min_size=1, max_size=12).filter(
    lambda r: any(x > 0 for x in r)
)
total_st = st.integers(min_value=-1_000_000_000, max_value=1_000_000_000)
ids_st = st.lists(
    st.text(alphabet="abcdefghij", min_size=1, max_size=4), min_size=2, max_size=8, unique=True
)


# ---------------------------------------------------------------- allocate


@given(total_st, ratios_st)
def test_allocate_sums_to_total(total: int, ratios: list[int]) -> None:
    assert sum(allocate(total, ratios)) == total


@given(total_st, ratios_st)
def test_allocate_parts_are_floor_or_ceil(total: int, ratios: list[int]) -> None:
    r_sum = sum(ratios)
    for part, r in zip(allocate(total, ratios), ratios, strict=True):
        exact = Fraction(total * r, r_sum)
        assert part in {
            exact.numerator // exact.denominator,
            -((-exact.numerator) // exact.denominator),
        }


@given(total_st, ratios_st)
def test_allocate_zero_ratio_gets_zero(total: int, ratios: list[int]) -> None:
    for part, r in zip(allocate(total, ratios), ratios, strict=True):
        if r == 0:
            assert part == 0


@given(total_st, ratios_st)
def test_allocate_is_deterministic(total: int, ratios: list[int]) -> None:
    assert allocate(total, ratios) == allocate(total, list(ratios))


@given(total_st, ratios_st)
def test_allocate_sign_symmetry(total: int, ratios: list[int]) -> None:
    assert allocate(-total, ratios) == [-x for x in allocate(total, ratios)]


@given(total_st, ratios_st, st.integers(min_value=1, max_value=50))
def test_allocate_scaling_invariant(total: int, ratios: list[int], k: int) -> None:
    assert allocate(total, [r * k for r in ratios]) == allocate(total, ratios)


def test_allocate_rejects_bool_and_float() -> None:
    with pytest.raises(DomainError) as exc:
        allocate(True, [1])
    assert exc.value.code == "invalid_amount"
    with pytest.raises(DomainError) as exc:
        allocate(10, [1.5])  # type: ignore[list-item]
    assert exc.value.code == "invalid_ratios"


# ---------------------------------------------------------- resolve_shares

amount_st = st.integers(min_value=-100_000_000, max_value=100_000_000).filter(lambda x: x != 0)


@given(amount_st, ids_st, st.data())
def test_resolve_shares_sum_and_participants(
    amount: int, ids: list[str], data: st.DataObject
) -> None:
    split_type = data.draw(st.sampled_from(["equal", "weights", "single", "personal"]))
    if split_type == "single":
        participants = [SplitParticipant(ids[0])]
    elif split_type == "weights":
        weights = data.draw(
            st.lists(
                st.integers(min_value=0, max_value=100), min_size=len(ids), max_size=len(ids)
            ).filter(lambda w: any(x > 0 for x in w))
        )
        participants = [SplitParticipant(i, weight=w) for i, w in zip(ids, weights, strict=True)]
    else:
        participants = [SplitParticipant(i) for i in ids]
    payer = ids[-1]
    shares = resolve_shares(amount, payer, split_type, participants)
    assert sum(s.amount_cents for s in shares) == amount
    if split_type == "personal":
        assert [(s.id, s.amount_cents) for s in shares] == [(payer, amount)]
    else:
        allowed = {p.id for p in participants}
        assert all(s.id in allowed for s in shares)
        if split_type == "weights":
            for s, p in zip(shares, participants, strict=True):
                if p.weight == 0:
                    assert s.amount_cents == 0


@given(amount_st, ids_st, st.data())
def test_resolve_shares_exact_mismatch_always_raises(
    amount: int, ids: list[str], data: st.DataObject
) -> None:
    exact = data.draw(
        st.lists(st.integers(-(10**6), 10**6), min_size=len(ids), max_size=len(ids)).filter(
            lambda xs: sum(xs) != amount
        )
    )
    participants = [SplitParticipant(i, exact_cents=x) for i, x in zip(ids, exact, strict=True)]
    with pytest.raises(DomainError) as exc:
        resolve_shares(amount, ids[0], "exact", participants)
    assert exc.value.code == "split_mismatch"


# ------------------------------------------------------------------ settle


@st.composite
def balanced_nets(draw: st.DrawFn) -> list[NetEntry]:
    ids = draw(ids_st)
    values = draw(
        st.lists(
            st.integers(min_value=-1_000_000, max_value=1_000_000),
            min_size=len(ids) - 1,
            max_size=len(ids) - 1,
        )
    )
    values.append(-sum(values))
    return [NetEntry(i, v) for i, v in zip(ids, values, strict=True)]


@given(balanced_nets())
def test_settle_zeroes_every_net(nets: list[NetEntry]) -> None:
    transfers = settle(nets)
    remaining = {n.id: n.net_cents for n in nets}
    for t in transfers:
        assert t.amount_cents > 0
        remaining[t.from_id] += t.amount_cents
        remaining[t.to_id] -= t.amount_cents
    assert all(v == 0 for v in remaining.values())


@given(balanced_nets())
def test_settle_transfer_count_bound(nets: list[NetEntry]) -> None:
    non_zero = sum(1 for n in nets if n.net_cents != 0)
    assert len(settle(nets)) <= max(non_zero - 1, 0)


@given(balanced_nets())
def test_settle_nobody_both_pays_and_receives(nets: list[NetEntry]) -> None:
    transfers = settle(nets)
    payers = {t.from_id for t in transfers}
    receivers = {t.to_id for t in transfers}
    assert not payers & receivers


@given(balanced_nets(), st.randoms(use_true_random=False))
def test_settle_deterministic_under_canonical_order(
    nets: list[NetEntry], rnd: random.Random
) -> None:
    canonical = sorted(nets, key=lambda n: n.id)
    shuffled = list(nets)
    rnd.shuffle(shuffled)
    assert settle(sorted(shuffled, key=lambda n: n.id)) == settle(canonical)
    assert settle(nets) == settle(list(nets))


@given(balanced_nets(), st.integers(min_value=1, max_value=1000))
def test_settle_requires_balanced(nets: list[NetEntry], delta: int) -> None:
    broken = [*nets[:-1], NetEntry(nets[-1].id, nets[-1].net_cents + delta)]
    with pytest.raises(DomainError) as exc:
        settle(broken)
    assert exc.value.code == "unbalanced_nets"


# -------------------------------------------------------- compute_balances


@given(ids_st, st.data())
def test_balances_sum_to_zero(ids: list[str], data: st.DataObject) -> None:
    expenses: list[LedgerExpense] = []
    for _ in range(data.draw(st.integers(0, 6))):
        amount = data.draw(amount_st)
        payer = data.draw(st.sampled_from(ids))
        subset = data.draw(st.lists(st.sampled_from(ids), min_size=1, unique=True))
        shares = resolve_shares(amount, payer, "equal", [SplitParticipant(i) for i in subset])
        personal = data.draw(st.booleans())
        expenses.append(LedgerExpense(payer, amount, shares, personal))
    balances = compute_balances(ids, expenses)
    assert sum(b.net_cents for b in balances) == 0
    assert [b.id for b in balances] == ids
