"""Households, invitation code and membership."""

from __future__ import annotations

import secrets
from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from split_ranch.core import clock
from split_ranch.core.actor import Actor, HouseholdActor
from split_ranch.core.errors import AppError, Conflict, NotFound, Unprocessable
from split_ranch.models import DEFAULT_SPLIT_RULE, Category, Household, HouseholdMember
from split_ranch.repositories import expenses as erepo
from split_ranch.repositories import households as repo
from split_ranch.schemas.households import (
    HouseholdCreate,
    HouseholdRead,
    HouseholdUpdate,
    InvitationPreview,
    InvitationRead,
    MemberRead,
    MemberRoleUpdate,
)
from split_ranch.use_cases.common import audit, require_active, require_admin
from split_ranch.use_cases.periods import create_first_period

# Default categories copied into every new household (Spanish first; UI translates by icon).
DEFAULT_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("Supermercado", "cart", "#4CAF50"),
    ("Alquiler", "home", "#795548"),
    ("Luz", "bolt", "#FFC107"),
    ("Agua", "droplet", "#03A9F4"),
    ("Gas", "flame", "#FF5722"),
    ("Internet", "wifi", "#3F51B5"),
    ("Transporte", "bus", "#009688"),
    ("Restaurantes", "utensils", "#E91E63"),
    ("Ocio", "ticket", "#9C27B0"),
    ("Salud", "heart", "#F44336"),
    ("Hogar", "sofa", "#8BC34A"),
    ("Otros", "dots", "#9E9E9E"),
)

INVITE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"  # base32
INVITE_VALID_FOR = timedelta(days=7)


def _validate_timezone(tz: str) -> None:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise Unprocessable(f"Unknown time zone {tz!r}") from exc


def _household_read(
    session: Session, household: Household, actor_member: HouseholdMember
) -> HouseholdRead:
    members = repo.list_members_with_users(session, household.id)
    return HouseholdRead(
        id=household.id,
        name=household.name,
        timezone=household.timezone,
        created_at=household.created_at,
        members=[
            MemberRead(
                id=m.id,
                user_id=m.user_id,
                display_name=u.display_name,
                role=m.role,
                status=m.status,
                sort_key=m.sort_key,
                joined_period_seq=m.joined_period_seq,
                left_period_seq=m.left_period_seq,
            )
            for m, u in members
        ],
        my_member_id=actor_member.id,
        my_role=actor_member.role,
    )


def _load(session: Session, actor: HouseholdActor) -> tuple[Household, HouseholdMember]:
    household = repo.get_household(session, actor.household_id)
    member = repo.get_member(session, actor.household_id, actor.member_id)
    if household is None or member is None:
        raise NotFound("Household not found")
    return household, member


def create_household(session: Session, actor: Actor, data: HouseholdCreate) -> HouseholdRead:
    _validate_timezone(data.timezone)
    household = Household(
        name=data.name.strip(),
        timezone=data.timezone,
        created_by=actor.user_id,
        split_rule=dict(DEFAULT_SPLIT_RULE),
    )
    session.add(household)
    session.flush()
    first = create_first_period(session, household)
    member = HouseholdMember(
        household_id=household.id,
        user_id=actor.user_id,
        role="admin",
        status="active",
        sort_key=0,
        joined_period_seq=first.seq,
    )
    session.add(member)
    for i, (name, icon, color) in enumerate(DEFAULT_CATEGORIES):
        session.add(
            Category(
                household_id=household.id,
                name=name,
                icon=icon,
                color=color,
                is_default=True,
                sort_key=i,
            )
        )
    audit(
        session,
        household_id=household.id,
        entity="household",
        entity_id=household.id,
        actor_user_id=actor.user_id,
        action="create",
        diff={"name": household.name, "timezone": household.timezone},
    )
    session.commit()
    return _household_read(session, household, member)


def get_household(session: Session, actor: HouseholdActor) -> HouseholdRead:
    household, member = _load(session, actor)
    return _household_read(session, household, member)


def update_household(
    session: Session, actor: HouseholdActor, data: HouseholdUpdate
) -> HouseholdRead:
    require_admin(actor)
    household = repo.get_household(session, actor.household_id, for_update=True)
    member = repo.get_member(session, actor.household_id, actor.member_id)
    if household is None or member is None:
        raise NotFound("Household not found")
    changes = data.model_dump(exclude_unset=True)
    if "timezone" in changes and changes["timezone"] is not None:
        _validate_timezone(changes["timezone"])
    diff: dict[str, object] = {}
    for key, value in changes.items():
        if value is None:
            continue
        old = getattr(household, key)
        if old != value:
            diff[key] = {"before": old, "after": value}
            setattr(household, key, value)
    if diff:
        audit(
            session,
            household_id=household.id,
            entity="household",
            entity_id=household.id,
            actor_user_id=actor.user_id,
            action="update",
            diff=diff,
        )
    session.commit()
    return _household_read(session, household, member)


# ------------------------------------------------------------ invitations


def _invite_valid(household: Household) -> bool:
    return (
        household.invite_code is not None
        and household.invite_expires_at is not None
        and household.invite_expires_at > clock.now()
    )


def _invitation_read(household: Household, base_url: str) -> InvitationRead:
    assert household.invite_code is not None and household.invite_expires_at is not None
    return InvitationRead(
        code=household.invite_code,
        url=f"{base_url.rstrip('/')}/join/{household.invite_code}",
        expires_at=household.invite_expires_at,
    )


def get_or_create_invitation(
    session: Session, actor: HouseholdActor, *, base_url: str
) -> InvitationRead:
    """The household's join code: the current one while valid, else a fresh one (7 days)."""
    require_admin(actor)
    household = repo.get_household(session, actor.household_id, for_update=True)
    if household is None:
        raise NotFound("Household not found")
    if not _invite_valid(household):
        household.invite_code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(8))
        household.invite_expires_at = clock.now() + INVITE_VALID_FOR
        session.commit()
    return _invitation_read(household, base_url)


def revoke_invitation(session: Session, actor: HouseholdActor) -> None:
    """Invalidate the current code; the next invitation gets a new one."""
    require_admin(actor)
    household = repo.get_household(session, actor.household_id, for_update=True)
    if household is None:
        raise NotFound("Household not found")
    household.invite_code = None
    household.invite_expires_at = None
    session.commit()


def _household_for_code(session: Session, code: str, *, for_update: bool = False) -> Household:
    household = repo.get_household_by_invite_code(
        session, code.strip().upper(), for_update=for_update
    )
    if household is None:
        raise NotFound("Invitation not found")
    if not _invite_valid(household):
        raise AppError("Invitation expired", code="invitation_expired", status=410)
    return household


def preview_invitation(session: Session, actor: Actor, code: str) -> InvitationPreview:
    household = _household_for_code(session, code)
    count = session.scalar(
        select(func.count())
        .select_from(HouseholdMember)
        .where(HouseholdMember.household_id == household.id, HouseholdMember.status != "left")
    )
    assert household.invite_expires_at is not None
    return InvitationPreview(
        household_name=household.name,
        member_count=int(count or 0),
        expires_at=household.invite_expires_at,
    )


def accept_invitation(session: Session, actor: Actor, code: str) -> HouseholdRead:
    from split_ranch.use_cases.rules import reresolve_open_expenses

    household = _household_for_code(session, code, for_update=True)
    existing = repo.get_membership(session, household.id, actor.user_id)
    if existing is not None and existing.status != "left":
        raise Conflict(
            "Already a member of this household",
            code="already_member",
            extra={"household_id": str(household.id), "member_id": str(existing.id)},
        )

    latest = erepo.get_latest_period(session, household.id, for_update=True)
    latest_seq = latest.seq if latest else 0
    # Joining takes part in the open period. With no open period the member joins the next
    # one: a closed period's balance must not change because someone joined.
    open_now = latest is not None and latest.status == "open"
    joined = latest_seq if open_now else latest_seq + 1

    max_sort = session.scalar(
        select(func.max(HouseholdMember.sort_key)).where(
            HouseholdMember.household_id == household.id
        )
    )
    sort_key = int(max_sort or 0) + 1
    if existing is not None:
        member = existing
        member.status = "active"
        member.role = "member"
        member.joined_period_seq = joined
        member.left_period_seq = None
        member.sort_key = sort_key
    else:
        member = HouseholdMember(
            household_id=household.id,
            user_id=actor.user_id,
            role="member",
            status="active",
            sort_key=sort_key,
            joined_period_seq=joined,
        )
        session.add(member)
    session.flush()
    audit(
        session,
        household_id=household.id,
        entity="household_member",
        entity_id=member.id,
        actor_user_id=actor.user_id,
        action="join",
        diff={"joined_period_seq": joined},
    )
    if open_now:
        # Whole-period membership: "all members" expenses of the open period include them now.
        reresolve_open_expenses(
            session,
            household.id,
            actor_user_id=actor.user_id,
            reason="member_joined",
            only_all_members=True,
        )
    session.commit()
    return _household_read(session, household, member)


# ---------------------------------------------------------------- members


def _admin_count(session: Session, household_id: UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(HouseholdMember)
            .where(
                HouseholdMember.household_id == household_id,
                HouseholdMember.role == "admin",
                HouseholdMember.status == "active",
            )
        )
        or 0
    )


def change_member_role(
    session: Session, actor: HouseholdActor, member_id: UUID, data: MemberRoleUpdate
) -> HouseholdRead:
    require_admin(actor)
    member = repo.get_member(session, actor.household_id, member_id, for_update=True)
    if member is None:
        raise NotFound("Member not found")
    if member.status != "active":
        raise Conflict("Only active members can change role")
    if (
        member.role == "admin"
        and data.role != "admin"
        and _admin_count(session, actor.household_id) <= 1
    ):
        raise Conflict("Cannot demote the last admin", code="last_admin")
    if member.role != data.role:
        audit(
            session,
            household_id=actor.household_id,
            entity="household_member",
            entity_id=member.id,
            actor_user_id=actor.user_id,
            action="role_change",
            diff={"before": member.role, "after": data.role},
        )
        member.role = data.role
    session.commit()
    return get_household(session, actor)


def _start_leaving(session: Session, actor: HouseholdActor, member: HouseholdMember) -> None:
    household = repo.get_household(session, actor.household_id)
    assert household is not None
    if member.status != "active":
        raise Conflict("Member is already leaving", code="already_leaving")
    others = session.scalar(
        select(func.count())
        .select_from(HouseholdMember)
        .where(
            HouseholdMember.household_id == actor.household_id,
            HouseholdMember.status == "active",
            HouseholdMember.id != member.id,
        )
    )
    if member.role == "admin" and _admin_count(session, actor.household_id) <= 1 and others:
        raise Conflict("Promote another admin before leaving", code="last_admin")
    latest = erepo.get_latest_period(session, household.id)
    member.status = "leaving"
    # Whole-period rule: the member stays in the current (latest) period and settles it.
    member.left_period_seq = max(latest.seq if latest else 1, member.joined_period_seq)
    audit(
        session,
        household_id=actor.household_id,
        entity="household_member",
        entity_id=member.id,
        actor_user_id=actor.user_id,
        action="leave",
        diff={"left_period_seq": member.left_period_seq},
    )


def leave_household(session: Session, actor: HouseholdActor) -> HouseholdRead:
    require_active(actor)
    member = repo.get_member(session, actor.household_id, actor.member_id, for_update=True)
    assert member is not None
    _start_leaving(session, actor, member)
    session.commit()
    return get_household(session, actor)


def remove_member(session: Session, actor: HouseholdActor, member_id: UUID) -> HouseholdRead:
    require_admin(actor)
    member = repo.get_member(session, actor.household_id, member_id, for_update=True)
    if member is None:
        raise NotFound("Member not found")
    _start_leaving(session, actor, member)
    session.commit()
    return get_household(session, actor)
