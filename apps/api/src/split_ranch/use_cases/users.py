"""Users: ensure_user and profile."""

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
from split_ranch.models import DEFAULT_NOTIFICATION_PREFS, Group, GroupMember, User
from split_ranch.schemas.groups import MembershipRead, MeRead, MeUpdate, UserRead
from split_ranch.schemas.notifications import NotificationPrefs


class _EnsureUserCache:
    """Process-local cache: skip the upsert when the same claims were seen recently.

    Bounded: past `max_entries`, expired entries are dropped, and if that is not enough the
    whole cache is cleared (a miss only costs one upsert).
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max_entries
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
        now = time.monotonic()
        with self._lock:
            if user_id not in self._seen and len(self._seen) >= self._max_entries:
                self._seen = {k: v for k, v in self._seen.items() if v[0] > now}
                if len(self._seen) >= self._max_entries:
                    self._seen.clear()
            self._seen[user_id] = (now + ttl, fingerprint)

    def __len__(self) -> int:
        return len(self._seen)


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
        select(GroupMember, Group.name)
        .join(Group, Group.id == GroupMember.group_id)
        .where(
            GroupMember.user_id == actor.user_id,
            GroupMember.status == "active",
            Group.deleted_at.is_(None),
        )
        .order_by(GroupMember.created_at)
    ).all()
    base = UserRead.model_validate(user)
    return MeRead(
        **base.model_dump(),
        notifications=NotificationPrefs.model_validate(
            {**DEFAULT_NOTIFICATION_PREFS, **(user.notification_prefs or {})}
        ),
        memberships=[
            MembershipRead(
                group_id=m.group_id,
                group_name=name,
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
    if data.notifications is not None:
        changes = data.notifications.model_dump(exclude_none=True)
        # A new dict, so SQLAlchemy sees the JSONB column as changed.
        user.notification_prefs = {
            **DEFAULT_NOTIFICATION_PREFS,
            **(user.notification_prefs or {}),
            **changes,
        }
    session.commit()
    return get_me(session, actor)
