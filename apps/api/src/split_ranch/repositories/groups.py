"""Group-scoped queries: every function takes `group_id`."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from split_ranch.models import Category, CategoryPreset, Group, GroupMember, User


def get_group(session: Session, group_id: UUID, *, for_update: bool = False) -> Group | None:
    stmt = select(Group).where(Group.id == group_id, Group.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def get_membership(session: Session, group_id: UUID, user_id: UUID) -> GroupMember | None:
    return session.scalars(
        select(GroupMember)
        .join(Group, Group.id == GroupMember.group_id)
        .where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
            Group.deleted_at.is_(None),
        )
    ).first()


def list_members(session: Session, group_id: UUID) -> Sequence[GroupMember]:
    """All members (any status) in canonical order: sort_key ASC, id ASC."""
    return session.scalars(
        select(GroupMember)
        .where(GroupMember.group_id == group_id)
        .order_by(GroupMember.sort_key, GroupMember.id)
    ).all()


def list_members_with_users(session: Session, group_id: UUID) -> Sequence[tuple[GroupMember, User]]:
    rows = session.execute(
        select(GroupMember, User)
        .join(User, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group_id)
        .order_by(GroupMember.sort_key, GroupMember.id)
    ).all()
    return [(m, u) for m, u in rows]


def members_with_users_by_group(
    session: Session, group_ids: Sequence[UUID]
) -> dict[UUID, list[tuple[GroupMember, User]]]:
    """`list_members_with_users` for several groups in one query (same order per group)."""
    result: dict[UUID, list[tuple[GroupMember, User]]] = {gid: [] for gid in group_ids}
    if not group_ids:
        return result
    rows = session.execute(
        select(GroupMember, User)
        .join(User, User.id == GroupMember.user_id)
        .where(GroupMember.group_id.in_(group_ids))
        .order_by(GroupMember.group_id, GroupMember.sort_key, GroupMember.id)
    ).all()
    for m, u in rows:
        result[m.group_id].append((m, u))
    return result


def get_member(
    session: Session, group_id: UUID, member_id: UUID, *, for_update: bool = False
) -> GroupMember | None:
    stmt = select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.id == member_id)
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def active_members(session: Session, group_id: UUID) -> Sequence[GroupMember]:
    """Active members in canonical order: who "everyone" means when a split is resolved."""
    return session.scalars(
        select(GroupMember)
        .where(GroupMember.group_id == group_id, GroupMember.status == "active")
        .order_by(GroupMember.sort_key, GroupMember.id)
    ).all()


def list_groups_for_user(session: Session, user_id: UUID) -> Sequence[tuple[Group, GroupMember]]:
    """The user's live groups where they are an active member, oldest first."""
    rows = session.execute(
        select(Group, GroupMember)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(
            GroupMember.user_id == user_id,
            GroupMember.status == "active",
            Group.deleted_at.is_(None),
        )
        .order_by(Group.created_at, Group.id)
    ).all()
    return [(g, m) for g, m in rows]


def get_category(
    session: Session, group_id: UUID, category_id: UUID, *, include_archived: bool = True
) -> Category | None:
    stmt = select(Category).where(Category.group_id == group_id, Category.id == category_id)
    if not include_archived:
        stmt = stmt.where(Category.archived_at.is_(None))
    return session.scalars(stmt).first()


def list_categories(
    session: Session, group_id: UUID, *, include_archived: bool = False
) -> Sequence[Category]:
    stmt = select(Category).where(Category.group_id == group_id)
    if not include_archived:
        stmt = stmt.where(Category.archived_at.is_(None))
    return session.scalars(stmt.order_by(Category.sort_key, Category.name)).all()


def category_name_taken(
    session: Session, group_id: UUID, name: str, exclude_id: UUID | None = None
) -> bool:
    stmt = select(Category.id).where(
        Category.group_id == group_id,
        Category.archived_at.is_(None),
        func.lower(Category.name) == name.strip().lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(Category.id != exclude_id)
    return session.scalars(stmt).first() is not None


def get_group_by_invite_code(
    session: Session, code: str, *, for_update: bool = False
) -> Group | None:
    stmt = select(Group).where(Group.invite_code == code, Group.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def list_category_presets(session: Session, group_id: UUID) -> Sequence[CategoryPreset]:
    """The group's presets whose category is still active, by keyword."""
    return session.scalars(
        select(CategoryPreset)
        .join(
            Category,
            (Category.id == CategoryPreset.category_id)
            & (Category.group_id == CategoryPreset.group_id),
        )
        .where(CategoryPreset.group_id == group_id, Category.archived_at.is_(None))
        .order_by(func.lower(CategoryPreset.keyword), CategoryPreset.id)
    ).all()


def get_category_preset(session: Session, group_id: UUID, preset_id: UUID) -> CategoryPreset | None:
    return session.scalars(
        select(CategoryPreset).where(
            CategoryPreset.group_id == group_id, CategoryPreset.id == preset_id
        )
    ).first()


def category_preset_keyword_taken(session: Session, group_id: UUID, keyword: str) -> bool:
    stmt = select(CategoryPreset.id).where(
        CategoryPreset.group_id == group_id,
        func.lower(CategoryPreset.keyword) == keyword.strip().lower(),
    )
    return session.scalars(stmt).first() is not None
