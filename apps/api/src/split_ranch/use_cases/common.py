"""Helpers shared by use cases: authorisation, versions, history."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from split_ranch.core.actor import GroupActor
from split_ranch.core.errors import Forbidden, PreconditionFailed, PreconditionRequired
from split_ranch.models import History


def require_admin(actor: GroupActor) -> None:
    if not actor.is_admin:
        raise Forbidden("Only the group admin can do this")


def require_active(actor: GroupActor) -> None:
    """Members who left are not members any more (the API answers 404 to them)."""
    if actor.status == "left":
        raise Forbidden("Former members cannot change this group")


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
