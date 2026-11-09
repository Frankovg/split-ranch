"""Household-scoped queries: every function takes `household_id`."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from split_ranch.models import (
    Category,
    Household,
    HouseholdMember,
    SplitRule,
    SplitRuleShare,
    User,
)


def get_household(
    session: Session, household_id: UUID, *, for_update: bool = False
) -> Household | None:
    stmt = select(Household).where(Household.id == household_id, Household.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def get_membership(session: Session, household_id: UUID, user_id: UUID) -> HouseholdMember | None:
    return session.scalars(
        select(HouseholdMember)
        .join(Household, Household.id == HouseholdMember.household_id)
        .where(
            HouseholdMember.household_id == household_id,
            HouseholdMember.user_id == user_id,
            Household.deleted_at.is_(None),
        )
    ).first()


def list_members(session: Session, household_id: UUID) -> Sequence[HouseholdMember]:
    """All members (any status) in canonical order: sort_key ASC, id ASC."""
    return session.scalars(
        select(HouseholdMember)
        .where(HouseholdMember.household_id == household_id)
        .order_by(HouseholdMember.sort_key, HouseholdMember.id)
    ).all()


def list_members_with_users(
    session: Session, household_id: UUID
) -> Sequence[tuple[HouseholdMember, User]]:
    rows = session.execute(
        select(HouseholdMember, User)
        .join(User, User.id == HouseholdMember.user_id)
        .where(HouseholdMember.household_id == household_id)
        .order_by(HouseholdMember.sort_key, HouseholdMember.id)
    ).all()
    return [(m, u) for m, u in rows]


def get_member(
    session: Session, household_id: UUID, member_id: UUID, *, for_update: bool = False
) -> HouseholdMember | None:
    stmt = select(HouseholdMember).where(
        HouseholdMember.household_id == household_id, HouseholdMember.id == member_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def period_members(session: Session, household_id: UUID, seq: int) -> Sequence[HouseholdMember]:
    """Members who take part in period `seq` (whole-period membership)."""
    return session.scalars(
        select(HouseholdMember)
        .where(
            HouseholdMember.household_id == household_id,
            HouseholdMember.joined_period_seq <= seq,
            or_(
                HouseholdMember.left_period_seq.is_(None),
                HouseholdMember.left_period_seq >= seq,
            ),
        )
        .order_by(HouseholdMember.sort_key, HouseholdMember.id)
    ).all()


def get_category(
    session: Session, household_id: UUID, category_id: UUID, *, include_archived: bool = True
) -> Category | None:
    stmt = select(Category).where(Category.household_id == household_id, Category.id == category_id)
    if not include_archived:
        stmt = stmt.where(Category.archived_at.is_(None))
    return session.scalars(stmt).first()


def list_categories(
    session: Session, household_id: UUID, *, include_archived: bool = False
) -> Sequence[Category]:
    stmt = select(Category).where(Category.household_id == household_id)
    if not include_archived:
        stmt = stmt.where(Category.archived_at.is_(None))
    return session.scalars(stmt.order_by(Category.sort_key, Category.name)).all()


def category_name_taken(
    session: Session, household_id: UUID, name: str, exclude_id: UUID | None = None
) -> bool:
    stmt = select(Category.id).where(
        Category.household_id == household_id,
        Category.archived_at.is_(None),
        func.lower(Category.name) == name.strip().lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(Category.id != exclude_id)
    return session.scalars(stmt).first() is not None


def get_rule(
    session: Session,
    household_id: UUID,
    scope: str,
    category_id: UUID | None = None,
    *,
    for_update: bool = False,
) -> SplitRule | None:
    conds = [SplitRule.household_id == household_id, SplitRule.scope == scope]
    if category_id is not None:
        conds.append(SplitRule.category_id == category_id)
    stmt = select(SplitRule).where(and_(*conds))
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def list_rules(session: Session, household_id: UUID) -> Sequence[SplitRule]:
    return session.scalars(
        select(SplitRule)
        .where(SplitRule.household_id == household_id)
        .order_by(SplitRule.scope, SplitRule.created_at)
    ).all()


def rule_shares(session: Session, household_id: UUID, rule_id: UUID) -> Sequence[SplitRuleShare]:
    return session.scalars(
        select(SplitRuleShare)
        .where(SplitRuleShare.household_id == household_id, SplitRuleShare.split_rule_id == rule_id)
        .order_by(SplitRuleShare.sort_key)
    ).all()
