"""Rule precedence (docs/03 §2): override -> recurring -> category -> default -> equal.

Pure functions over already-loaded data; the domain does the arithmetic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from split_ranch.domain import DomainError, SplitParticipant, SplitType, resolve_shares
from split_ranch.schemas.split import (
    EqualSplit,
    ExactSplit,
    PercentagesSplit,
    PersonalSplit,
    SingleSplit,
    SplitSpec,
    WeightsSplit,
)


@dataclass(frozen=True)
class RuleRow:
    member_id: UUID
    weight: int | None = None
    basis_points: int | None = None
    amount_cents: int | None = None


@dataclass(frozen=True)
class RuleData:
    split_type: str
    rows: Sequence[RuleRow] = ()


@dataclass(frozen=True)
class ResolvedShare:
    member_id: UUID
    amount_cents: int
    weight: int | None = None
    basis_points: int | None = None
    exact_cents: int | None = None


@dataclass
class Resolution:
    split_type: str
    split_origin: str
    participant_mode: str
    rule_fallback: bool
    shares: list[ResolvedShare] = field(default_factory=list)


@dataclass(frozen=True)
class _Plan:
    split_type: SplitType
    participants: list[SplitParticipant]
    participant_mode: str


def _sorted(ids: Sequence[UUID], canonical: Sequence[UUID]) -> list[UUID]:
    index = {m: i for i, m in enumerate(canonical)}
    return sorted(ids, key=lambda m: (index.get(m, len(index)), str(m)))


def _check_members(ids: Sequence[UUID], allowed: set[UUID]) -> None:
    for m in ids:
        if m not in allowed:
            raise DomainError("invalid_split", f"member {m} does not take part in this period")


def _plan_from_override(
    spec: SplitSpec,
    participants: Sequence[UUID] | None,
    period_members: Sequence[UUID],
    allowed: set[UUID],
    canonical: Sequence[UUID],
) -> _Plan:
    explicit = not isinstance(spec, EqualSplit | PersonalSplit) or (
        isinstance(spec, EqualSplit) and spec.shares
    )
    if explicit and participants is not None:
        raise DomainError("invalid_split", "use either split.shares or participants, not both")

    if isinstance(spec, PersonalSplit):
        return _Plan("personal", [], "subset")
    if isinstance(spec, EqualSplit):
        if spec.shares:
            ids = [s.member_id for s in spec.shares]
            mode = "subset"
        elif participants is not None:
            ids = list(participants)
            mode = "subset"
        else:
            ids = list(period_members)
            mode = "all"
        _check_members(ids, allowed)
        return _Plan("equal", [SplitParticipant(str(m)) for m in _sorted(ids, canonical)], mode)
    if isinstance(spec, WeightsSplit):
        by_id_w = {s.member_id: s.weight for s in spec.shares}
        _check_members(list(by_id_w), allowed)
        return _Plan(
            "weights",
            [
                SplitParticipant(str(m), weight=by_id_w[m])
                for m in _sorted(list(by_id_w), canonical)
            ],
            "subset",
        )
    if isinstance(spec, PercentagesSplit):
        by_id_bp = {s.member_id: s.basis_points for s in spec.shares}
        _check_members(list(by_id_bp), allowed)
        return _Plan(
            "percentages",
            [
                SplitParticipant(str(m), basis_points=by_id_bp[m])
                for m in _sorted(list(by_id_bp), canonical)
            ],
            "subset",
        )
    if isinstance(spec, ExactSplit):
        by_id_x = {s.member_id: s.amount_cents for s in spec.shares}
        _check_members(list(by_id_x), allowed)
        return _Plan(
            "exact",
            [
                SplitParticipant(str(m), exact_cents=by_id_x[m])
                for m in _sorted(list(by_id_x), canonical)
            ],
            "subset",
        )
    assert isinstance(spec, SingleSplit)
    member = spec.shares[0].member_id
    _check_members([member], allowed)
    return _Plan("single", [SplitParticipant(str(member))], "subset")


def _plan_subset_from_rule(
    rule: RuleData | None, subset: Sequence[UUID], canonical: Sequence[UUID]
) -> _Plan:
    """A participant subset is an override that keeps the rule's weights when possible."""
    ordered = _sorted(list(dict.fromkeys(subset)), canonical)
    if rule is not None and rule.split_type in ("weights", "percentages"):
        by_id = {
            r.member_id: (r.weight if rule.split_type == "weights" else r.basis_points)
            for r in rule.rows
        }
        if all(by_id.get(m) is not None for m in ordered) and any(by_id[m] for m in ordered):
            return _Plan(
                "weights",
                [SplitParticipant(str(m), weight=by_id[m]) for m in ordered],
                "subset",
            )
    return _Plan("equal", [SplitParticipant(str(m)) for m in ordered], "subset")


def _plan_from_rule(
    rule: RuleData, amount_cents: int, period_members: Sequence[UUID]
) -> _Plan | None:
    """Apply a stored rule to the period members; None means "not applicable" (fallback)."""
    present = set(period_members)
    rows = [r for r in rule.rows if r.member_id in present]
    index = {m: i for i, m in enumerate(period_members)}
    rows.sort(key=lambda r: index[r.member_id])
    st = rule.split_type
    if st == "personal":
        return _Plan("personal", [], "subset")
    if st == "equal":
        if not rule.rows:
            return _Plan("equal", [SplitParticipant(str(m)) for m in period_members], "all")
        if not rows:
            return None
        return _Plan("equal", [SplitParticipant(str(r.member_id)) for r in rows], "subset")
    if st == "weights":
        if not any(r.weight for r in rows):
            return None
        return _Plan(
            "weights",
            [SplitParticipant(str(r.member_id), weight=r.weight or 0) for r in rows],
            "subset",
        )
    if st == "percentages":
        if not any(r.basis_points for r in rows):
            return None
        if len(rows) == len(rule.rows):
            return _Plan(
                "percentages",
                [SplitParticipant(str(r.member_id), basis_points=r.basis_points) for r in rows],
                "subset",
            )
        # Some members are absent: basis points become weights (implicit re-normalisation).
        return _Plan(
            "weights",
            [SplitParticipant(str(r.member_id), weight=r.basis_points or 0) for r in rows],
            "subset",
        )
    if st == "exact":
        if len(rows) != len(rule.rows) or sum(r.amount_cents or 0 for r in rows) != amount_cents:
            return None
        return _Plan(
            "exact",
            [SplitParticipant(str(r.member_id), exact_cents=r.amount_cents) for r in rows],
            "subset",
        )
    if st == "single":
        if len(rows) != 1:
            return None
        return _Plan("single", [SplitParticipant(str(rows[0].member_id))], "subset")
    return None


def _execute(plan: _Plan, amount_cents: int, payer_id: UUID) -> list[ResolvedShare]:
    shares = resolve_shares(amount_cents, str(payer_id), plan.split_type, plan.participants)
    inputs = {p.id: p for p in plan.participants}
    out: list[ResolvedShare] = []
    for s in shares:
        p = inputs.get(s.id)
        out.append(
            ResolvedShare(
                member_id=UUID(s.id),
                amount_cents=s.amount_cents,
                weight=p.weight if p else None,
                basis_points=p.basis_points if p else None,
                exact_cents=p.exact_cents if p else None,
            )
        )
    return out


def resolve_expense_split(
    *,
    amount_cents: int,
    payer_member_id: UUID,
    override: SplitSpec | None,
    participants: Sequence[UUID] | None,
    category_rule: RuleData | None,
    default_rule: RuleData | None,
    period_members: Sequence[UUID],
    canonical_order: Sequence[UUID],
    allowed_members: set[UUID] | None = None,
) -> Resolution:
    """Resolve the split of one expense following the precedence chain.

    `period_members` are in canonical order; `allowed_members` widens who may appear in an
    explicit override (used by adjustments that reproduce an older period's split).
    """
    allowed = set(period_members) | (allowed_members or set())

    if override is not None:
        plan = _plan_from_override(override, participants, period_members, allowed, canonical_order)
        return Resolution(
            plan.split_type,
            "override",
            plan.participant_mode,
            False,
            _execute(plan, amount_cents, payer_member_id),
        )

    if participants is not None:
        _check_members(participants, allowed)
        plan = _plan_subset_from_rule(category_rule or default_rule, participants, canonical_order)
        return Resolution(
            plan.split_type,
            "override",
            "subset",
            False,
            _execute(plan, amount_cents, payer_member_id),
        )

    fallback = False
    # Recurring rules come with recurring expenses (post-MVP).
    for origin, rule in (("category", category_rule), ("household_default", default_rule)):
        if rule is None:
            continue
        rule_plan = _plan_from_rule(rule, amount_cents, period_members)
        if rule_plan is None:
            fallback = True
            continue
        return Resolution(
            rule_plan.split_type,
            origin,
            rule_plan.participant_mode,
            fallback,
            _execute(rule_plan, amount_cents, payer_member_id),
        )

    if not period_members:
        raise DomainError("invalid_split", "the period has no members")
    plan = _Plan("equal", [SplitParticipant(str(m)) for m in period_members], "all")
    return Resolution(
        "equal",
        "household_default",
        "all",
        fallback,
        _execute(plan, amount_cents, payer_member_id),
    )


def spec_member_ids(spec: SplitSpec) -> list[UUID]:
    """Members a split names explicitly (empty for "everyone" and personal splits)."""
    if isinstance(spec, PersonalSplit):
        return []
    if isinstance(spec, EqualSplit):
        return [s.member_id for s in spec.shares or []]
    return [s.member_id for s in spec.shares]


def rule_from_spec(spec: SplitSpec) -> RuleData:
    """A stored household/category rule (SplitSpec JSON) as resolution input."""
    if isinstance(spec, PersonalSplit):
        return RuleData("personal")
    if isinstance(spec, WeightsSplit):
        return RuleData("weights", [RuleRow(s.member_id, weight=s.weight) for s in spec.shares])
    if isinstance(spec, PercentagesSplit):
        return RuleData(
            "percentages",
            [RuleRow(s.member_id, basis_points=s.basis_points) for s in spec.shares],
        )
    if isinstance(spec, ExactSplit):
        return RuleData(
            "exact", [RuleRow(s.member_id, amount_cents=s.amount_cents) for s in spec.shares]
        )
    return RuleData(spec.split_type, [RuleRow(m) for m in spec_member_ids(spec)])


def spec_from_stored(split_type: str, shares: Sequence[ResolvedShare]) -> SplitSpec:
    """Rebuild an explicit override from stored share inputs (used by adjustments/edits)."""
    if split_type == "personal":
        return PersonalSplit(split_type="personal")
    if split_type == "equal":
        return EqualSplit.model_validate(
            {"split_type": "equal", "shares": [{"member_id": s.member_id} for s in shares]},
            strict=False,
        )
    if split_type == "weights":
        return WeightsSplit.model_validate(
            {
                "split_type": "weights",
                "shares": [{"member_id": s.member_id, "weight": s.weight or 0} for s in shares],
            },
            strict=False,
        )
    if split_type == "percentages":
        return PercentagesSplit.model_validate(
            {
                "split_type": "percentages",
                "shares": [
                    {"member_id": s.member_id, "basis_points": s.basis_points or 0} for s in shares
                ],
            },
            strict=False,
        )
    if split_type == "single":
        return SingleSplit.model_validate(
            {"split_type": "single", "shares": [{"member_id": shares[0].member_id}]}, strict=False
        )
    return ExactSplit.model_validate(
        {
            "split_type": "exact",
            "shares": [
                {
                    "member_id": s.member_id,
                    "amount_cents": s.exact_cents if s.exact_cents is not None else s.amount_cents,
                }
                for s in shares
            ],
        },
        strict=False,
    )
