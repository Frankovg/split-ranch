"""Helpers shared by use cases: authorisation, versions, history."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from split_ranch.core.actor import GroupActor
from split_ranch.core.errors import Forbidden, NotFound, PreconditionFailed, PreconditionRequired
from split_ranch.models import History
from split_ranch.repositories import groups as grepo


def require_admin(actor: GroupActor) -> None:
    if not actor.is_admin:
        raise Forbidden("Only the group admin can do this")


def lock_group_for_balance_write(session: Session, group_id: UUID) -> None:
    """Take the group row FOR SHARE before validating members of a balance write.

    Leaving, removing a member and deleting the group hold the same row FOR UPDATE while
    they check the balance, so an expense or payment cannot slip in between that check and
    the member's departure: it waits, then sees the member as left (or the group as
    deleted, re-checked by PostgreSQL after the wait). Concurrent writes only share it.
    """
    if grepo.get_group(session, group_id, for_share=True) is None:
        raise NotFound("Group not found")


def check_version(
    expected: int | None,
    current: int,
    *,
    current_body: Any = None,
    required: bool = True,
) -> None:
    """Optimistic locking: compare the If-Match version with the stored one."""
    if expected is None:
        if required:
            raise PreconditionRequired("If-Match header with the current version is required")
        return
    if expected != current:
        raise PreconditionFailed(
            f"Resource is at version {current}, not {expected}",
            extra={"current": current_body} if current_body is not None else None,
            headers={"ETag": f'"{current}"'},
        )


def audit(
    session: Session,
    *,
    group_id: UUID,
    entity: str,
    entity_id: UUID,
    actor_user_id: UUID | None,
    action: str,
    diff: dict[str, Any],
    reason: str | None = None,
) -> None:
    """Record a group event (group, member, category, rule, payment...) in `history`."""
    session.add(
        History(
            group_id=group_id,
            entity=entity,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            action=action,
            reason=reason,
            after=diff,
        )
    )
