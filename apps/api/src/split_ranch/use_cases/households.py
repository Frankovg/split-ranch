"""Households, invitations and membership."""

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
from split_ranch.models import (
    Category,
    Household,
    HouseholdMember,
    Invitation,
    SplitRule,
    User,
)
from split_ranch.repositories import households as repo
from split_ranch.schemas.households import (
    HouseholdCreate,
    HouseholdRead,
    HouseholdUpdate,
    InvitationAccept,
    InvitationCreate,
    InvitationPreview,
    InvitationRead,
    MemberRead,
    MemberRoleUpdate,
)
from split_ranch.use_cases.common import audit, check_version, require_active, require_admin

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
AUTO_CURRENT_UNTIL_DAY = 10


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
        currency=household.currency,
        grace_days=household.grace_days,
        auto_close=household.auto_close,
        version=household.version,
        created_at=household.created_at,
        members=[
            MemberRead(
                id=m.id,
                user_id=m.user_id,
                display_name=m.display_name_override or u.display_name,
                role=m.role,
                status=m.status,
                sort_key=m.sort_key,
                joined_period=m.joined_period,
                left_period=m.left_period,
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
    household = Household(name=data.name.strip(), timezone=data.timezone, created_by=actor.user_id)
    session.add(household)
    session.flush()
    month = clock.month_start(clock.today_in(data.timezone))
    member = HouseholdMember(
        household_id=household.id,
        user_id=actor.user_id,
        role="admin",
        status="active",
        sort_key=0,
        joined_period=month,
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
    session.add(
        SplitRule(
            household_id=household.id,
            scope="household_default",
            split_type="equal",
            updated_by=actor.user_id,
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
    session: Session, actor: HouseholdActor, data: HouseholdUpdate, if_match: int | None
) -> HouseholdRead:
    require_admin(actor)
    household = repo.get_household(session, actor.household_id, for_update=True)
    member = repo.get_member(session, actor.household_id, actor.member_id)
    if household is None or member is None:
        raise NotFound("Household not found")
    check_version(
        if_match, household.version, current_body=_household_read(session, household, member)
    )
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
        household.version += 1
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


def _invitation_read(inv: Invitation, base_url: str) -> InvitationRead:
    return InvitationRead(
        id=inv.id,
        code=inv.code,
        url=f"{base_url.rstrip('/')}/join/{inv.code}",
        expires_at=inv.expires_at,
        max_uses=inv.max_uses,
        uses=inv.uses,
        start_period=inv.start_period,
    )


def create_invitation(
    session: Session, actor: HouseholdActor, data: InvitationCreate, *, base_url: str
) -> InvitationRead:
    require_admin(actor)
    code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(8))
    inv = Invitation(
        household_id=actor.household_id,
        code=code,
        created_by=actor.user_id,
        expires_at=clock.now() + timedelta(days=data.expires_in_days),
        max_uses=data.max_uses,
        start_period=data.start_period,
    )
    session.add(inv)
    session.commit()
    return _invitation_read(inv, base_url)


def revoke_invitation(session: Session, actor: HouseholdActor, invitation_id: UUID) -> None:
    require_admin(actor)
    inv = session.scalars(
        select(Invitation).where(
            Invitation.household_id == actor.household_id, Invitation.id == invitation_id
        )
    ).first()
    if inv is None:
        raise NotFound("Invitation not found")
    if inv.revoked_at is None:
        inv.revoked_at = clock.now()
    session.commit()


def _usable_invitation(session: Session, code: str, *, for_update: bool = False) -> Invitation:
    stmt = select(Invitation).where(Invitation.code == code.strip().upper())
    if for_update:
        stmt = stmt.with_for_update()
    inv = session.scalars(stmt).first()
    if inv is None or repo.get_household(session, inv.household_id) is None:
        raise NotFound("Invitation not found")
    if inv.revoked_at is not None or inv.expires_at <= clock.now():
        raise AppError("Invitation expired or revoked", code="invitation_expired", status=410)
    if inv.uses >= inv.max_uses:
        raise Conflict("Invitation has no uses left", code="invitation_exhausted")
    return inv


def preview_invitation(session: Session, actor: Actor, code: str) -> InvitationPreview:
    inv = _usable_invitation(session, code)
    household = repo.get_household(session, inv.household_id)
    assert household is not None
    inviter = session.get(User, inv.created_by)
    count = session.scalar(
        select(func.count())
        .select_from(HouseholdMember)
        .where(HouseholdMember.household_id == inv.household_id, HouseholdMember.status != "left")
    )
    return InvitationPreview(
        household_name=household.name,
        inviter=inviter.display_name if inviter else None,
        member_count=int(count or 0),
        expires_at=inv.expires_at,
    )


def accept_invitation(
    session: Session, actor: Actor, code: str, data: InvitationAccept
) -> HouseholdRead:
    from split_ranch.use_cases.rules import reresolve_open_expenses

    inv = _usable_invitation(session, code, for_update=True)
    household = repo.get_household(session, inv.household_id)
    assert household is not None
    existing = repo.get_membership(session, household.id, actor.user_id)
    if existing is not None and existing.status != "left":
        raise Conflict(
            "Already a member of this household",
            code="already_member",
            extra={"household_id": str(household.id), "member_id": str(existing.id)},
        )

    today = clock.today_in(household.timezone)
    current = clock.month_start(today)
    start = data.start_period or inv.start_period
    if start is None:
        start = "current" if today.day <= AUTO_CURRENT_UNTIL_DAY else "next"
    joined = current if start == "current" else clock.next_month(current)

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
        member.joined_period = joined
        member.left_period = None
        member.sort_key = sort_key
    else:
        member = HouseholdMember(
            household_id=household.id,
            user_id=actor.user_id,
            role="member",
            status="active",
            sort_key=sort_key,
            joined_period=joined,
        )
        session.add(member)
    inv.uses += 1
    session.flush()
    audit(
        session,
        household_id=household.id,
        entity="household_member",
        entity_id=member.id,
        actor_user_id=actor.user_id,
        action="join",
        diff={"invitation_id": str(inv.id), "start_period": start},
    )
    if start == "current":
        # Full-month membership: "all members" expenses of the open period include them now.
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
    current = clock.month_start(clock.today_in(household.timezone))
    member.status = "leaving"
    # Full-month rule: the member stays in the current period and must settle it.
    member.left_period = max(current, member.joined_period)
    audit(
        session,
        household_id=actor.household_id,
        entity="household_member",
        entity_id=member.id,
        actor_user_id=actor.user_id,
        action="leave",
        diff={"left_period": member.left_period.isoformat()},
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
