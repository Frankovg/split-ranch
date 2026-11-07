"""Categories and split rules (household default + per category)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from split_ranch.core import clock
from split_ranch.core.actor import HouseholdActor
from split_ranch.core.errors import Conflict, NotFound, Unprocessable
from split_ranch.domain import BASIS_POINTS_TOTAL
from split_ranch.models import Category, SplitRule, SplitRuleShare
from split_ranch.repositories import households as hrepo
from split_ranch.schemas.households import CategoryCreate, CategoryRead, CategoryUpdate
from split_ranch.schemas.split import (
    EqualSplit,
    ExactSplit,
    PercentagesSplit,
    PersonalSplit,
    RuleShareRead,
    SingleSplit,
    SplitRuleRead,
    SplitRulesRead,
    SplitSpec,
    WeightsSplit,
)
from split_ranch.use_cases.common import audit, require_admin
from split_ranch.use_cases.expenses import reresolve_open_expenses

__all__ = [
    "archive_category",
    "create_category",
    "delete_category_rule",
    "list_categories",
    "list_rules",
    "reresolve_open_expenses",
    "set_category_rule",
    "set_default_rule",
    "update_category",
]


# ------------------------------------------------------------- categories


def list_categories(
    session: Session, actor: HouseholdActor, *, include_archived: bool = False
) -> list[CategoryRead]:
    return [
        CategoryRead.model_validate(c)
        for c in hrepo.list_categories(
            session, actor.household_id, include_archived=include_archived
        )
    ]


def create_category(session: Session, actor: HouseholdActor, data: CategoryCreate) -> CategoryRead:
    require_admin(actor)
    name = data.name.strip()
    if hrepo.category_name_taken(session, actor.household_id, name):
        raise Conflict("A category with this name already exists", code="category_exists")
    sort_key = data.sort_key
    if sort_key is None:
        current = session.scalar(
            select(func.max(Category.sort_key)).where(Category.household_id == actor.household_id)
        )
        sort_key = int(current or 0) + 1
    category = Category(
        household_id=actor.household_id,
        name=name,
        icon=data.icon,
        color=data.color,
        sort_key=sort_key,
    )
    session.add(category)
    session.flush()
    audit(
        session,
        household_id=actor.household_id,
        entity="category",
        entity_id=category.id,
        actor_user_id=actor.user_id,
        action="create",
        diff={"name": name},
    )
    session.commit()
    return CategoryRead.model_validate(category)


def _category(session: Session, actor: HouseholdActor, category_id: UUID) -> Category:
    category = hrepo.get_category(session, actor.household_id, category_id)
    if category is None:
        raise NotFound("Category not found")
    return category


def update_category(
    session: Session, actor: HouseholdActor, category_id: UUID, data: CategoryUpdate
) -> CategoryRead:
    require_admin(actor)
    category = _category(session, actor, category_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name"):
        changes["name"] = changes["name"].strip()
        if hrepo.category_name_taken(session, actor.household_id, changes["name"], category.id):
            raise Conflict("A category with this name already exists", code="category_exists")
    diff = {}
    for key, value in changes.items():
        if key in ("name", "sort_key") and value is None:
            continue
        if getattr(category, key) != value:
            diff[key] = {"before": getattr(category, key), "after": value}
            setattr(category, key, value)
    if diff:
        audit(
            session,
            household_id=actor.household_id,
            entity="category",
            entity_id=category.id,
            actor_user_id=actor.user_id,
            action="update",
            diff=diff,
        )
    session.commit()
    return CategoryRead.model_validate(category)


def archive_category(session: Session, actor: HouseholdActor, category_id: UUID) -> None:
    require_admin(actor)
    category = _category(session, actor, category_id)
    if category.archived_at is None:
        category.archived_at = clock.now()
        audit(
            session,
            household_id=actor.household_id,
            entity="category",
            entity_id=category.id,
            actor_user_id=actor.user_id,
            action="archive",
            diff={},
        )
    session.commit()


# ------------------------------------------------------------------ rules


def _rule_read(session: Session, household_id: UUID, rule: SplitRule) -> SplitRuleRead:
    return SplitRuleRead(
        id=rule.id,
        scope=rule.scope,
        category_id=rule.category_id,
        split_type=rule.split_type,
        version=rule.version,
        shares=[
            RuleShareRead(
                member_id=s.member_id,
                weight=s.weight,
                basis_points=s.basis_points,
                amount_cents=s.amount_cents,
            )
            for s in hrepo.rule_shares(session, household_id, rule.id)
        ],
    )


def list_rules(session: Session, actor: HouseholdActor) -> SplitRulesRead:
    rules = hrepo.list_rules(session, actor.household_id)
    default = next((r for r in rules if r.scope == "household_default"), None)
    return SplitRulesRead(
        default=_rule_read(session, actor.household_id, default) if default else None,
        categories=[
            _rule_read(session, actor.household_id, r) for r in rules if r.scope == "category"
        ],
    )


def _rows(spec: SplitSpec) -> list[SplitRuleShare]:
    if isinstance(spec, PersonalSplit):
        return []
    if isinstance(spec, EqualSplit):
        return [SplitRuleShare(member_id=s.member_id) for s in spec.shares or []]
    if isinstance(spec, WeightsSplit):
        return [SplitRuleShare(member_id=s.member_id, weight=s.weight) for s in spec.shares]
    if isinstance(spec, PercentagesSplit):
        if sum(s.basis_points for s in spec.shares) != BASIS_POINTS_TOTAL:
            raise Unprocessable(
                f"basis points must sum to {BASIS_POINTS_TOTAL}", code="split_mismatch"
            )
        return [
            SplitRuleShare(member_id=s.member_id, basis_points=s.basis_points) for s in spec.shares
        ]
    if isinstance(spec, ExactSplit):
        return [
            SplitRuleShare(member_id=s.member_id, amount_cents=s.amount_cents) for s in spec.shares
        ]
    assert isinstance(spec, SingleSplit)
    return [SplitRuleShare(member_id=spec.shares[0].member_id)]


def _upsert_rule(
    session: Session,
    actor: HouseholdActor,
    scope: str,
    spec: SplitSpec,
    category_id: UUID | None = None,
) -> SplitRule:
    rows = _rows(spec)
    members = {m.id: m for m in hrepo.list_members(session, actor.household_id)}
    for row in rows:
        member = members.get(row.member_id)
        if member is None or member.status == "left":
            raise Unprocessable(
                f"Member {row.member_id} is not in this household", code="invalid_split"
            )
    rule = hrepo.get_rule(session, actor.household_id, scope, category_id, for_update=True)
    before = None
    if rule is None:
        rule = SplitRule(
            household_id=actor.household_id,
            scope=scope,
            category_id=category_id,
            split_type=spec.split_type,
            updated_by=actor.user_id,
        )
        session.add(rule)
        session.flush()
    else:
        before = _rule_read(session, actor.household_id, rule).model_dump(mode="json")
        session.execute(
            delete(SplitRuleShare).where(
                SplitRuleShare.household_id == actor.household_id,
                SplitRuleShare.split_rule_id == rule.id,
            )
        )
        rule.split_type = spec.split_type
        rule.version += 1
        rule.updated_by = actor.user_id
    order = list(members)
    for row in sorted(rows, key=lambda r: order.index(r.member_id)):
        row.split_rule_id = rule.id
        row.household_id = actor.household_id
        row.sort_key = order.index(row.member_id)
        session.add(row)
    session.flush()
    audit(
        session,
        household_id=actor.household_id,
        entity="split_rule",
        entity_id=rule.id,
        actor_user_id=actor.user_id,
        action="set",
        diff={
            "before": before,
            "after": _rule_read(session, actor.household_id, rule).model_dump(mode="json"),
        },
    )
    return rule


def set_default_rule(session: Session, actor: HouseholdActor, spec: SplitSpec) -> SplitRuleRead:
    require_admin(actor)
    rule = _upsert_rule(session, actor, "household_default", spec)
    reresolve_open_expenses(
        session,
        actor.household_id,
        actor_user_id=actor.user_id,
        reason="rule_changed",
        split_origin="household_default",
    )
    session.commit()
    return _rule_read(session, actor.household_id, rule)


def set_category_rule(
    session: Session, actor: HouseholdActor, category_id: UUID, spec: SplitSpec
) -> SplitRuleRead:
    require_admin(actor)
    category = _category(session, actor, category_id)
    if category.archived_at is not None:
        raise Conflict("Category is archived", code="category_archived")
    rule = _upsert_rule(session, actor, "category", spec, category_id)
    # Open-period expenses of this category that follow a rule pick up the new one.
    for origin in ("category", "household_default"):
        reresolve_open_expenses(
            session,
            actor.household_id,
            actor_user_id=actor.user_id,
            reason="rule_changed",
            split_origin=origin,
            category_id=category_id,
        )
    session.commit()
    return _rule_read(session, actor.household_id, rule)


def delete_category_rule(session: Session, actor: HouseholdActor, category_id: UUID) -> None:
    require_admin(actor)
    _category(session, actor, category_id)
    rule = hrepo.get_rule(session, actor.household_id, "category", category_id, for_update=True)
    if rule is None:
        return
    audit(
        session,
        household_id=actor.household_id,
        entity="split_rule",
        entity_id=rule.id,
        actor_user_id=actor.user_id,
        action="delete",
        diff={"before": _rule_read(session, actor.household_id, rule).model_dump(mode="json")},
    )
    session.delete(rule)
    session.flush()
    reresolve_open_expenses(
        session,
        actor.household_id,
        actor_user_id=actor.user_id,
        reason="rule_changed",
        split_origin="category",
        category_id=category_id,
    )
    session.commit()
