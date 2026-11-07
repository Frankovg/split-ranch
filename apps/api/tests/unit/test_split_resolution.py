"""Rule precedence resolver (pure) and small helpers."""

from __future__ import annotations

import uuid

import pytest

from split_ranch.core.ids import uuid7
from split_ranch.domain import DomainError
from split_ranch.schemas.split import EqualSplit, ExactSplit
from split_ranch.use_cases.split_resolution import (
    RuleData,
    RuleRow,
    resolve_expense_split,
)

J, F, A = (uuid.UUID(int=i) for i in (1, 2, 3))
MEMBERS = [J, F, A]


def _resolve(**kw: object):  # type: ignore[no-untyped-def]
    args: dict[str, object] = {
        "amount_cents": 10000,
        "payer_member_id": F,
        "override": None,
        "participants": None,
        "category_rule": None,
        "default_rule": RuleData("equal"),
        "period_members": MEMBERS,
        "canonical_order": MEMBERS,
    }
    args.update(kw)
    return resolve_expense_split(**args)  # type: ignore[arg-type]


def test_default_equal_all() -> None:
    r = _resolve()
    assert (r.split_origin, r.participant_mode, r.rule_fallback) == (
        "household_default",
        "all",
        False,
    )
    assert [s.amount_cents for s in r.shares] == [3334, 3333, 3333]


def test_no_rules_falls_to_equal() -> None:
    r = _resolve(default_rule=None)
    assert r.split_origin == "household_default" and r.split_type == "equal"


def test_category_beats_default() -> None:
    rule = RuleData(
        "percentages",
        [
            RuleRow(J, basis_points=4000),
            RuleRow(F, basis_points=3000),
            RuleRow(A, basis_points=3000),
        ],
    )
    r = _resolve(amount_cents=120000, category_rule=rule)
    assert r.split_origin == "category"
    assert [s.amount_cents for s in r.shares] == [48000, 36000, 36000]


def test_percentages_with_absent_member_become_weights() -> None:
    rule = RuleData("percentages", [RuleRow(J, basis_points=6000), RuleRow(F, basis_points=4000)])
    r = _resolve(amount_cents=1000, category_rule=rule, period_members=[J, A])
    assert r.split_type == "weights" and [s.member_id for s in r.shares] == [J]


def test_single_absent_member_falls_back() -> None:
    r = _resolve(category_rule=RuleData("single", [RuleRow(uuid.UUID(int=9))]))
    assert r.rule_fallback is True and r.split_origin == "household_default"


def test_override_and_subset() -> None:
    r = _resolve(participants=[A, J])
    assert r.split_origin == "override" and [s.member_id for s in r.shares] == [J, A]
    r = _resolve(override=EqualSplit(split_type="equal"))
    assert r.split_origin == "override" and r.participant_mode == "all"
    with pytest.raises(DomainError) as exc:
        _resolve(
            override=ExactSplit.model_validate(
                {"split_type": "exact", "shares": [{"member_id": str(J), "amount_cents": 1}]},
                strict=False,
            )
        )
    assert exc.value.code == "split_mismatch"


def test_override_member_outside_period() -> None:
    with pytest.raises(DomainError) as exc:
        _resolve(participants=[uuid.UUID(int=42)])
    assert exc.value.code == "invalid_split"


def test_uuid7_shape_and_order() -> None:
    ids = [uuid7() for _ in range(50)]
    assert all(i.version == 7 and i.variant == uuid.RFC_4122 for i in ids)
    assert len(set(ids)) == 50
    # Time-ordered at millisecond granularity.
    assert sorted(i.int >> 80 for i in ids) == [i.int >> 80 for i in ids]
