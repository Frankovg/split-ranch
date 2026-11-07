"""Users: ensure_user, profile, push tokens."""

from __future__ import annotations

import threading
import time
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from split_ranch.core.actor import Actor
from split_ranch.core.errors import NotFound
from split_ranch.core.security import TokenClaims
from split_ranch.models import Household, HouseholdMember, PushToken, User
from split_ranch.schemas.households import MembershipRead, MeRead, MeUpdate, PushTokenIn, UserRead


class _EnsureUserCache:
    """Process-local cache: skip the upsert when the same claims were seen recently."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen: dict[UUID, tuple[float, tuple[object, ...]]] = {}

    def fresh(self, user_id: UUID, fingerprint: tuple[object, ...], ttl: float) -> bool:
        if ttl <= 0:
            return False
        with self._lock:
            hit = self._seen.get(user_id)
            return hit is not None and hit[1] == fingerprint and hit[0] > time.monotonic()

    def remember(self, user_id: UUID, fingerprint: tuple[object, ...], ttl: float) -> None:
        if ttl <= 0:
            return
        with self._lock:
            self._seen[user_id] = (time.monotonic() + ttl, fingerprint)


ensure_user_cache = _EnsureUserCache()


def ensure_user(session: Session, claims: TokenClaims, *, cache_seconds: float = 0) -> Actor:
    """Idempotent upsert of `app.users` from the token claims."""
    fingerprint = (claims.email, claims.display_name, claims.avatar_url)
    if ensure_user_cache.fresh(claims.user_id, fingerprint, cache_seconds):
        return Actor(user_id=claims.user_id)
    stmt = insert(User).values(
        id=claims.user_id,
        email=claims.email,
        display_name=claims.display_name,
        avatar_url=claims.avatar_url,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[User.id],
        set_={
            "email": stmt.excluded.email,
            "avatar_url": func.coalesce(stmt.excluded.avatar_url, User.avatar_url),
            # The user may have renamed themselves in the app: keep their choice.
            "display_name": func.coalesce(User.display_name, stmt.excluded.display_name),
        },
        where=(
            User.email.is_distinct_from(stmt.excluded.email)
            | User.display_name.is_(None)
            | User.avatar_url.is_distinct_from(
                func.coalesce(stmt.excluded.avatar_url, User.avatar_url)
            )
        ),
    )
    session.execute(stmt)
    session.commit()
    ensure_user_cache.remember(claims.user_id, fingerprint, cache_seconds)
    return Actor(user_id=claims.user_id)


def _user(session: Session, user_id: UUID) -> User:
    user = session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFound("User not found")
    return user


def get_me(session: Session, actor: Actor) -> MeRead:
    user = _user(session, actor.user_id)
    rows = session.execute(
        select(HouseholdMember, Household.name)
        .join(Household, Household.id == HouseholdMember.household_id)
        .where(HouseholdMember.user_id == actor.user_id, Household.deleted_at.is_(None))
        .order_by(HouseholdMember.created_at)
    ).all()
    base = UserRead.model_validate(user)
    return MeRead(
        **base.model_dump(),
        memberships=[
            MembershipRead(
                household_id=m.household_id,
                household_name=name,
                member_id=m.id,
                role=m.role,
                status=m.status,
            )
            for m, name in rows
        ],
    )


def update_profile(session: Session, actor: Actor, data: MeUpdate) -> MeRead:
    user = _user(session, actor.user_id)
    if data.display_name is not None:
        user.display_name = data.display_name.strip()
    if data.locale is not None:
        user.locale = data.locale
    if data.payment_handles is not None:
        user.payment_handles = data.payment_handles.model_dump(exclude_none=True)
    session.commit()
    return get_me(session, actor)


def register_push_token(session: Session, actor: Actor, data: PushTokenIn) -> None:
    stmt = insert(PushToken).values(
        user_id=actor.user_id, expo_token=data.expo_token, platform=data.platform
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[PushToken.expo_token],
        set_={
            "user_id": actor.user_id,
            "platform": data.platform,
            "last_seen_at": func.now(),
            "disabled_at": None,
        },
    )
    session.execute(stmt)
    session.commit()


def delete_push_token(session: Session, actor: Actor, token: str) -> None:
    row = session.scalars(
        select(PushToken).where(PushToken.user_id == actor.user_id, PushToken.expo_token == token)
    ).first()
    if row is not None:
        session.delete(row)
        session.commit()
