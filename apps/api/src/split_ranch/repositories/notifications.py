"""Push tokens and the data a notification needs (recipients, names)."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from split_ranch.models import GroupMember, PushToken, User


def upsert_token(session: Session, user_id: UUID, token: str, platform: str, locale: str) -> None:
    """Register a device token. A token already stored (also for another user, after an
    account switch on the same phone) is moved to `user_id` and its pending ticket dropped."""
    stmt = insert(PushToken).values(user_id=user_id, token=token, platform=platform, locale=locale)
    stmt = stmt.on_conflict_do_update(
        index_elements=[PushToken.token],
        set_={
            "user_id": stmt.excluded.user_id,
            "platform": stmt.excluded.platform,
            "locale": stmt.excluded.locale,
            "updated_at": func.now(),
            # A ticket sent to the previous owner says nothing about this registration.
            "last_ticket_id": None,
            "last_ticket_at": None,
        },
    )
    session.execute(stmt)


def delete_token(session: Session, user_id: UUID, token: str) -> None:
    session.execute(delete(PushToken).where(PushToken.user_id == user_id, PushToken.token == token))


def delete_tokens(session: Session, ids: Collection[UUID]) -> None:
    if ids:
        session.execute(delete(PushToken).where(PushToken.id.in_(list(ids))))


def tokens_for_users(session: Session, user_ids: Collection[UUID]) -> Sequence[PushToken]:
    if not user_ids:
        return []
    return (
        session.execute(
            select(PushToken)
            .where(PushToken.user_id.in_(list(user_ids)))
            .order_by(PushToken.created_at, PushToken.id)
        )
        .scalars()
        .all()
    )


def set_ticket(
    session: Session, token_id: UUID, ticket_id: str | None, at: datetime | None
) -> None:
    session.execute(
        update(PushToken)
        .where(PushToken.id == token_id)
        .values(last_ticket_id=ticket_id, last_ticket_at=at)
    )


def active_member_users(session: Session, group_id: UUID) -> dict[UUID, UUID]:
    """member_id -> user_id for the group's active members."""
    rows = session.execute(
        select(GroupMember.id, GroupMember.user_id).where(
            GroupMember.group_id == group_id, GroupMember.status == "active"
        )
    ).all()
    return {row.id: row.user_id for row in rows}


def users_by_id(session: Session, user_ids: Collection[UUID]) -> dict[UUID, User]:
    if not user_ids:
        return {}
    rows = session.execute(
        select(User).where(User.id.in_(list(user_ids)), User.deleted_at.is_(None))
    ).scalars()
    return {u.id: u for u in rows}
