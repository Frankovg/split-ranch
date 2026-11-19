"""Groups, invitation code and membership.

Every active member has the same rights, except that the group's single admin (its
creator, or whoever the role passed to) is the only one who removes members and deletes
the group. A member can leave, or be removed, only with a zero balance and no payment
waiting for confirmation (decision D2). When the admin leaves, the role passes to the next
active member in canonical order (D1); the last member leaving deletes the group.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from split_ranch.core import clock
from split_ranch.core.actor import Actor, GroupActor
from split_ranch.core.errors import AppError, Conflict, NotFound, Unprocessable
from split_ranch.models import DEFAULT_SPLIT_RULE, Category, Group, GroupMember, Payment, User
from split_ranch.repositories import groups as repo
from split_ranch.schemas.groups import (
    GroupCreate,
    GroupDeleteIn,
    GroupRead,
    GroupUpdate,
    InvitationPreview,
    InvitationRead,
    MemberRead,
)
from split_ranch.use_cases.balance import compute_group_balance
from split_ranch.use_cases.common import audit, require_active, require_admin

# Default categories copied into every new group, alphabetical. The app names them by
# icon key in its own language; "Other" is the expense without a category (no row).
DEFAULT_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("Entertainment", "ticket", "#9C27B0"),
    ("Groceries", "cart", "#4CAF50"),
    ("Healthcare", "heart", "#F44336"),
    ("Home", "sofa", "#8BC34A"),
    ("Insurance", "shield", "#607D8B"),
    ("Rent and Services", "home", "#795548"),
    ("Restaurants and bars", "utensils", "#E91E63"),
    ("Shopping", "bag", "#FF9800"),
    ("Transport", "bus", "#009688"),
)

INVITE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"  # base32
INVITE_CODE_RE = re.compile(r"[A-Z2-7]{8}")
INVITE_VALID_FOR = timedelta(days=7)


def _validate_timezone(tz: str) -> None:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise Unprocessable(f"Unknown time zone {tz!r}") from exc


def _group_read(
    session: Session,
    group: Group,
    actor_member: GroupMember,
    members: Sequence[tuple[GroupMember, User]] | None = None,
) -> GroupRead:
    """`members` may be preloaded (group lists); otherwise they are queried here."""
    if members is None:
        members = repo.list_members_with_users(session, group.id)
    return GroupRead(
        id=group.id,
        name=group.name,
        timezone=group.timezone,
        created_at=group.created_at,
        members=[
            MemberRead(
                id=m.id,
                user_id=m.user_id,
                display_name=u.display_name,
                role=m.role,
                status=m.status,
                sort_key=m.sort_key,
                joined_at=m.joined_at,
                left_at=m.left_at,
            )
            for m, u in members
        ],
        my_member_id=actor_member.id,
        my_role=actor_member.role,
    )


def _locked_group(session: Session, group_id: UUID) -> Group:
    """The group row locked FOR UPDATE: serialises membership changes and deletion."""
    group = repo.get_group(session, group_id, for_update=True)
    if group is None:
        raise NotFound("Group not found")
    return group


def create_group(session: Session, actor: Actor, data: GroupCreate) -> GroupRead:
    _validate_timezone(data.timezone)
    group = Group(
        name=data.name.strip(),
        timezone=data.timezone,
        created_by=actor.user_id,
        split_rule=dict(DEFAULT_SPLIT_RULE),
    )
    session.add(group)
    session.flush()
    member = GroupMember(
        group_id=group.id,
        user_id=actor.user_id,
        role="admin",
        status="active",
        sort_key=0,
        joined_at=clock.now(),
    )
    session.add(member)
    for i, (name, icon, color) in enumerate(DEFAULT_CATEGORIES):
        session.add(
            Category(
                group_id=group.id,
                name=name,
                icon=icon,
                color=color,
                is_default=True,
                sort_key=i,
            )
        )
    session.flush()
    audit(
        session,
        group_id=group.id,
        entity="group",
        entity_id=group.id,
        actor_user_id=actor.user_id,
        action="create",
        diff={"name": group.name, "timezone": group.timezone},
    )
    session.commit()
    return _group_read(session, group, member)


def list_groups(session: Session, actor: Actor) -> list[GroupRead]:
    rows = repo.list_groups_for_user(session, actor.user_id)
    # One members query for every group instead of one per group.
    members = repo.members_with_users_by_group(session, [g.id for g, _ in rows])
    return [_group_read(session, g, m, members[g.id]) for g, m in rows]


def get_group(session: Session, actor: GroupActor) -> GroupRead:
    group = repo.get_group(session, actor.group_id)
    member = repo.get_member(session, actor.group_id, actor.member_id)
    if group is None or member is None:
        raise NotFound("Group not found")
    return _group_read(session, group, member)


def update_group(session: Session, actor: GroupActor, data: GroupUpdate) -> GroupRead:
    require_active(actor)
    group = _locked_group(session, actor.group_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("timezone") is not None:
        _validate_timezone(changes["timezone"])
    diff: dict[str, object] = {}
    for key, value in changes.items():
        if value is None:
            continue
        old = getattr(group, key)
        if old != value:
            diff[key] = {"before": old, "after": value}
            setattr(group, key, value)
    if diff:
        audit(
            session,
            group_id=group.id,
            entity="group",
            entity_id=group.id,
            actor_user_id=actor.user_id,
            action="update",
            diff=diff,
        )
    session.commit()
    return get_group(session, actor)


def _open_balances(session: Session, group_id: UUID) -> bool:
    result = compute_group_balance(session, group_id)
    return any(b.net_cents != 0 for b in result.balances) or bool(result.pending)


def _soft_delete(session: Session, group: Group, actor_user_id: UUID) -> None:
    group.deleted_at = clock.now()
    group.invite_code = None
    group.invite_expires_at = None
    audit(
        session,
        group_id=group.id,
        entity="group",
        entity_id=group.id,
        actor_user_id=actor_user_id,
        action="delete",
        diff={"name": group.name},
    )


def delete_group(session: Session, actor: GroupActor, data: GroupDeleteIn) -> None:
    """Soft delete by the admin, confirmed with the group's name, only with zero balances."""
    require_admin(actor)
    group = _locked_group(session, actor.group_id)
    if data.confirm_name.strip() != group.name:
        raise Unprocessable("The confirmation does not match the group name", code="confirm_name")
    if _open_balances(session, group.id):
        raise Conflict(
            "Settle every balance before deleting the group", code="group_has_open_balances"
        )
    _soft_delete(session, group, actor.user_id)
    session.commit()


# ------------------------------------------------------------ invitations


def _invite_valid(group: Group) -> bool:
    return (
        group.invite_code is not None
        and group.invite_expires_at is not None
        and group.invite_expires_at > clock.now()
    )


def _invitation_read(group: Group) -> InvitationRead:
    assert group.invite_code is not None and group.invite_expires_at is not None
    return InvitationRead(code=group.invite_code, expires_at=group.invite_expires_at)


def get_or_create_invitation(session: Session, actor: GroupActor) -> InvitationRead:
    """The group's join code: the current one while valid, else a fresh one (7 days)."""
    require_active(actor)
    group = _locked_group(session, actor.group_id)
    if not _invite_valid(group):
        group.invite_code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(8))
        group.invite_expires_at = clock.now() + INVITE_VALID_FOR
        audit(
            session,
            group_id=group.id,
            entity="group",
            entity_id=group.id,
            actor_user_id=actor.user_id,
            action="invite_code_created",
            diff={"expires_at": group.invite_expires_at.isoformat()},
        )
        session.commit()
    return _invitation_read(group)


def revoke_invitation(session: Session, actor: GroupActor) -> None:
    """Invalidate the current code; the next invitation gets a new one."""
    require_active(actor)
    group = _locked_group(session, actor.group_id)
    if group.invite_code is not None:
        group.invite_code = None
        group.invite_expires_at = None
        audit(
            session,
            group_id=group.id,
            entity="group",
            entity_id=group.id,
            actor_user_id=actor.user_id,
            action="invite_code_revoked",
            diff={},
        )
    session.commit()


def _group_for_code(session: Session, code: str, *, for_update: bool = False) -> Group:
    normalized = code.strip().upper()
    # A malformed code (e.g. with a NUL byte from a clipboard) cannot exist: 404, never a DB error
    if not INVITE_CODE_RE.fullmatch(normalized):
        raise NotFound("Invitation not found")
    group = repo.get_group_by_invite_code(session, normalized, for_update=for_update)
    if group is None:
        raise NotFound("Invitation not found")
    if not _invite_valid(group):
        raise AppError("Invitation expired", code="invitation_expired", status=410)
    return group


def preview_invitation(session: Session, actor: Actor, code: str) -> InvitationPreview:
    group = _group_for_code(session, code)
    count = session.scalar(
        select(func.count())
        .select_from(GroupMember)
        .where(GroupMember.group_id == group.id, GroupMember.status == "active")
    )
    assert group.invite_expires_at is not None
    return InvitationPreview(
        group_name=group.name,
        member_count=int(count or 0),
        expires_at=group.invite_expires_at,
    )


def accept_invitation(session: Session, actor: Actor, code: str) -> GroupRead:
    """Join with the code. Existing expenses are never re-split for the newcomer."""
    group = _group_for_code(session, code, for_update=True)
    existing = repo.get_membership(session, group.id, actor.user_id)
    if existing is not None and existing.status == "active":
        raise Conflict(
            "Already a member of this group",
            code="already_member",
            extra={"group_id": str(group.id), "member_id": str(existing.id)},
        )
    max_sort = session.scalar(
        select(func.max(GroupMember.sort_key)).where(GroupMember.group_id == group.id)
    )
    sort_key = int(max_sort or 0) + 1
    now = clock.now()
    if existing is not None:
        # Rejoining: the old row (and its history) comes back as a new member.
        member = existing
        member.status = "active"
        member.role = "member"
        member.joined_at = now
        member.left_at = None
        member.sort_key = sort_key
        action = "rejoin"
    else:
        member = GroupMember(
            group_id=group.id,
            user_id=actor.user_id,
            role="member",
            status="active",
            sort_key=sort_key,
            joined_at=now,
        )
        session.add(member)
        action = "join"
    session.flush()
    audit(
        session,
        group_id=group.id,
        entity="group_member",
        entity_id=member.id,
        actor_user_id=actor.user_id,
        action=action,
        diff={"user_id": str(actor.user_id)},
    )
    session.commit()
    return _group_read(session, group, member)


# ---------------------------------------------------------------- members


def _require_settled(session: Session, group_id: UUID, member: GroupMember) -> None:
    """D2: leaving needs a zero net and no payment of the member waiting for confirmation."""
    result = compute_group_balance(session, group_id)
    net = next((b.net_cents for b in result.balances if b.id == str(member.id)), 0)
    waiting = session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(
            Payment.group_id == group_id,
            Payment.status.in_(("sent", "disputed")),
            (Payment.from_member_id == member.id) | (Payment.to_member_id == member.id),
        )
    )
    if net != 0 or waiting:
        raise Conflict(
            "The member's balance must be settled first",
            code="member_has_open_balance",
            extra={"net_cents": net, "pending_payments": int(waiting or 0)},
        )


def _leave(session: Session, group: Group, member: GroupMember, actor_user_id: UUID) -> None:
    others = [m for m in repo.active_members(session, group.id) if m.id != member.id]
    if not others:
        # The last member leaving deletes the group (nothing can be owed with one member).
        member.status = "left"
        member.left_at = clock.now()
        _soft_delete(session, group, actor_user_id)
        return
    was_admin = member.role == "admin"
    member.status = "left"
    member.left_at = clock.now()
    member.role = "member"
    # Flush the departure first so the one-admin unique index never sees two admins.
    session.flush()
    audit(
        session,
        group_id=group.id,
        entity="group_member",
        entity_id=member.id,
        actor_user_id=actor_user_id,
        action="leave" if actor_user_id == member.user_id else "remove",
        diff={"user_id": str(member.user_id)},
    )
    if was_admin:
        heir = others[0]  # canonical order: sort_key, id
        heir.role = "admin"
        session.flush()
        audit(
            session,
            group_id=group.id,
            entity="group_member",
            entity_id=heir.id,
            actor_user_id=actor_user_id,
            action="admin_handover",
            diff={"from_member_id": str(member.id)},
        )


def leave_group(session: Session, actor: GroupActor) -> None:
    require_active(actor)
    group = _locked_group(session, actor.group_id)
    member = repo.get_member(session, group.id, actor.member_id, for_update=True)
    assert member is not None
    _require_settled(session, group.id, member)
    _leave(session, group, member, actor.user_id)
    session.commit()


def remove_member(session: Session, actor: GroupActor, member_id: UUID) -> GroupRead:
    require_admin(actor)
    group = _locked_group(session, actor.group_id)
    member = repo.get_member(session, group.id, member_id, for_update=True)
    if member is None or member.status != "active":
        raise NotFound("Member not found")
    if member.id == actor.member_id:
        raise Conflict("Use leave to leave the group", code="cannot_remove_self")
    _require_settled(session, group.id, member)
    _leave(session, group, member, actor.user_id)
    session.commit()
    return get_group(session, actor)
