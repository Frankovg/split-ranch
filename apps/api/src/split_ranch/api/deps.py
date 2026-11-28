"""FastAPI dependencies: identity from the JWT, membership from the DB."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import sentry_sdk
import structlog
from fastapi import BackgroundTasks, Depends, Header, Request
from sqlalchemy.orm import Session, sessionmaker

from split_ranch.core.actor import Actor, GroupActor
from split_ranch.core.db import get_session
from split_ranch.core.errors import NotFound, Unauthenticated, Unprocessable
from split_ranch.core.logging import hash_user_id
from split_ranch.core.observability import set_sentry_user
from split_ranch.core.rate_limit import RateLimiter
from split_ranch.core.security import TokenVerifier
from split_ranch.core.settings import Settings
from split_ranch.integrations.expo_push import ExpoPushClient
from split_ranch.repositories import groups as hrepo
from split_ranch.use_cases.notifications import (
    NotificationEvent,
    Notifier,
    NullNotifier,
    dispatch_safely,
)
from split_ranch.use_cases.users import ensure_user

SessionDep = Annotated[Session, Depends(get_session)]


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def bind_log_context(request: Request, **values: str) -> None:
    """Adds `values` to this request's log lines, the middleware's access log included.

    Sync dependencies run in a worker thread with a copy of the context, so contextvars
    bound here never reach the middleware; `request.state` (shared through the ASGI scope)
    carries them there.
    """
    structlog.contextvars.bind_contextvars(**values)
    context: dict[str, str] = getattr(request.state, "log_context", {})
    request.state.log_context = {**context, **values}


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
    # Before any DB work, so a flooding client costs no queries.
    limiter: RateLimiter = request.app.state.user_rate_limiter
    limiter.check(claims.user_id)
    actor = ensure_user(session, claims, cache_seconds=settings.ensure_user_cache_seconds)
    bind_log_context(request, user=hash_user_id(actor.user_id))
    set_sentry_user(actor.user_id)
    return actor


ActorDep = Annotated[Actor, Depends(get_actor)]


def limit_invitations(request: Request, actor: ActorDep) -> None:
    """Extra per-user limit on endpoints that take an invite code (guessing attempts)."""
    limiter: RateLimiter = request.app.state.invite_rate_limiter
    limiter.check(actor.user_id)


def get_group_actor(
    request: Request, group_id: UUID, actor: ActorDep, session: SessionDep
) -> GroupActor:
    """Non-members get 404 so the group's existence does not leak."""
    member = hrepo.get_membership(session, group_id, actor.user_id)
    # Members who left are not members any more: same 404 as for outsiders.
    if member is None or member.status != "active":
        raise NotFound("Group not found")
    bind_log_context(request, group_id=str(group_id))
    sentry_sdk.set_tag("group_id", str(group_id))
    return GroupActor(
        user_id=actor.user_id,
        group_id=group_id,
        member_id=member.id,
        role=member.role,
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


class BackgroundNotifier:
    """Queues each event as a background task: it is sent after the response."""

    def __init__(
        self,
        tasks: BackgroundTasks,
        session_factory: sessionmaker[Session],
        client: ExpoPushClient,
    ) -> None:
        self._tasks = tasks
        self._session_factory = session_factory
        self._client = client

    def notify(self, event: NotificationEvent) -> None:
        self._tasks.add_task(dispatch_safely, self._session_factory, self._client, event)


def get_notifier(request: Request, background_tasks: BackgroundTasks) -> Notifier:
    client: ExpoPushClient | None = request.app.state.push_client
    if client is None:
        return NullNotifier()
    return BackgroundNotifier(background_tasks, request.app.state.session_factory, client)


NotifierDep = Annotated[Notifier, Depends(get_notifier)]
