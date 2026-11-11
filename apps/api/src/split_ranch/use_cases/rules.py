"""Categories and split rules (household default + per category)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from split_ranch.core import clock
from split_ranch.core.actor import HouseholdActor
from split_ranch.core.errors import Conflict, NotFound, Unprocessable
from split_ranch.domain import BASIS_POINTS_TOTAL
from split_ranch.models import Category, Household
from split_ranch.repositories import households as hrepo
from split_ranch.schemas.households import CategoryCreate, CategoryRead, CategoryUpdate
from split_ranch.schemas.split import (
    CategoryRuleRead,
    PercentagesSplit,
    SplitRulesRead,
    SplitSpec,
    spec_from_json,
    spec_to_json,
)
from split_ranch.use_cases.common import audit, require_admin
from split_ranch.use_cases.expenses import reresolve_open_expenses
from split_ranch.use_cases.split_resolution import spec_member_ids

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
#
# A rule is the `SplitSpec` JSON stored on the household (default) or on a category.


def list_rules(session: Session, actor: HouseholdActor) -> SplitRulesRead:
    household = _household(session, actor)
    return SplitRulesRead(
        default=spec_from_json(household.split_rule),
        categories=[
            CategoryRuleRead(category_id=c.id, split=spec_from_json(c.split_rule))
            for c in hrepo.list_categories(session, actor.household_id, include_archived=True)
            if c.split_rule is not None
        ],
    )


def _household(session: Session, actor: HouseholdActor, *, for_update: bool = False) -> Household:
    household = hrepo.get_household(session, actor.household_id, for_update=for_update)
    if household is None:
        raise NotFound("Household not found")
    return household


def _validated_rule(session: Session, actor: HouseholdActor, spec: SplitSpec) -> dict[str, Any]:
    """Check the members and percentages of a rule and return its JSON to store."""
    if isinstance(spec, PercentagesSplit) and (
        sum(s.basis_points for s in spec.shares) != BASIS_POINTS_TOTAL
    ):
        raise Unprocessable(f"basis points must sum to {BASIS_POINTS_TOTAL}", code="split_mismatch")
    members = {m.id: m for m in hrepo.list_members(session, actor.household_id)}
    for member_id in spec_member_ids(spec):
        member = members.get(member_id)
        if member is None or member.status == "left":
            raise Unprocessable(
                f"Member {member_id} is not in this household", code="invalid_split"
            )
    return spec_to_json(spec)


def _record_rule_change(
    session: Session,
    actor: HouseholdActor,
    entity_id: UUID,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    audit(
        session,
        household_id=actor.household_id,
        entity="split_rule",
        entity_id=entity_id,
        actor_user_id=actor.user_id,
        action=action,
        diff={"before": before, "after": after},
    )


def set_default_rule(session: Session, actor: HouseholdActor, spec: SplitSpec) -> SplitSpec:
    require_admin(actor)
    household = _household(session, actor, for_update=True)
    rule = _validated_rule(session, actor, spec)
    _record_rule_change(session, actor, household.id, "set", household.split_rule, rule)
    household.split_rule = rule
    session.flush()
    reresolve_open_expenses(
        session,
        actor.household_id,
        actor_user_id=actor.user_id,
        reason="rule_changed",
        split_origin="household_default",
    )
    session.commit()
    return spec_from_json(rule)


def set_category_rule(
    session: Session, actor: HouseholdActor, category_id: UUID, spec: SplitSpec
) -> CategoryRuleRead:
    require_admin(actor)
    category = _category(session, actor, category_id)
    if category.archived_at is not None:
        raise Conflict("Category is archived", code="category_archived")
    rule = _validated_rule(session, actor, spec)
    _record_rule_change(session, actor, category.id, "set", category.split_rule, rule)
    category.split_rule = rule
    session.flush()
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
    return CategoryRuleRead(category_id=category.id, split=spec_from_json(rule))


def delete_category_rule(session: Session, actor: HouseholdActor, category_id: UUID) -> None:
    require_admin(actor)
    category = _category(session, actor, category_id)
    if category.split_rule is None:
        return
    _record_rule_change(session, actor, category.id, "delete", category.split_rule, None)
    category.split_rule = None
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
