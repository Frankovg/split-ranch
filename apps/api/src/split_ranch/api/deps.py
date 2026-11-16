"""FastAPI dependencies: identity from the JWT, membership from the DB."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import sentry_sdk
import structlog
from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from split_ranch.core.actor import Actor, GroupActor
from split_ranch.core.db import get_session
from split_ranch.core.errors import NotFound, Unauthenticated, Unprocessable
from split_ranch.core.logging import hash_user_id
from split_ranch.core.observability import set_sentry_user
from split_ranch.core.security import TokenVerifier
from split_ranch.core.settings import Settings
from split_ranch.repositories import groups as hrepo
from split_ranch.use_cases.users import ensure_user

SessionDep = Annotated[Session, Depends(get_session)]


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_actor(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Actor:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthenticated("Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    verifier: TokenVerifier = request.app.state.token_verifier
    claims = verifier.verify(authorization[7:].strip())
    actor = ensure_user(session, claims, cache_seconds=settings.ensure_user_cache_seconds)
    structlog.contextvars.bind_contextvars(user=hash_user_id(actor.user_id))
    set_sentry_user(actor.user_id)
    return actor


ActorDep = Annotated[Actor, Depends(get_actor)]


def get_group_actor(group_id: UUID, actor: ActorDep, session: SessionDep) -> GroupActor:
    """Non-members get 404 so the group's existence does not leak."""
    member = hrepo.get_membership(session, group_id, actor.user_id)
    # Members who left are not members any more: same 404 as for outsiders.
    if member is None or member.status != "active":
        raise NotFound("Group not found")
    structlog.contextvars.bind_contextvars(group_id=str(group_id))
    sentry_sdk.set_tag("group_id", str(group_id))
    return GroupActor(
        user_id=actor.user_id,
        group_id=group_id,
        member_id=member.id,
        role=member.role,
        status=member.status,
    )


GroupActorDep = Annotated[GroupActor, Depends(get_group_actor)]


def parse_if_match(if_match: Annotated[str | None, Header()] = None) -> int | None:
    """Accepts `"3"`, `W/"3"` or `3`."""
    if if_match is None:
        return None
    value = if_match.strip()
    if value.startswith("W/"):
        value = value[2:]
    value = value.strip('"')
    try:
        return int(value)
    except ValueError as exc:
        raise Unprocessable("If-Match must be a version number") from exc


IfMatchDep = Annotated[int | None, Depends(parse_if_match)]


def etag(version: int) -> dict[str, str]:
    return {"ETag": f'"{version}"'}
