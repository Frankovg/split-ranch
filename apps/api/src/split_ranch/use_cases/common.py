"""Helpers shared by use cases: authorisation, versions, audit."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from split_ranch.core.actor import HouseholdActor
from split_ranch.core.errors import Forbidden, PreconditionFailed, PreconditionRequired
from split_ranch.models import AuditLog


def require_admin(actor: HouseholdActor) -> None:
    if not actor.is_admin:
        raise Forbidden("Only household admins can do this")


def require_active(actor: HouseholdActor) -> None:
    """Members who already left keep read access only."""
    if actor.status == "left":
        raise Forbidden("Former members have read-only access")


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
    household_id: UUID | None,
    entity: str,
    entity_id: UUID,
    actor_user_id: UUID | None,
    action: str,
    diff: dict[str, Any],
) -> None:
    session.add(
        AuditLog(
            household_id=household_id,
            entity=entity,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            action=action,
            diff=diff,
        )
    )
