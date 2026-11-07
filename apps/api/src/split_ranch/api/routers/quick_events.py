"""Quick splits."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from split_ranch.api.deps import ActorDep, IfMatchDep, SessionDep, SettingsDep, etag
from split_ranch.schemas.common import Page
from split_ranch.schemas.quick import (
    QuickEventIn,
    QuickEventRead,
    QuickEventSummary,
    QuickShareLinkRead,
    SharedQuickEventRead,
)
from split_ranch.use_cases import quick_events

router = APIRouter(prefix="/quick-events", tags=["quick-events"])


@router.get("/shared/{token}")
def get_shared(token: str, session: SessionDep) -> SharedQuickEventRead:
    """Public, read-only (no auth)."""
    return quick_events.get_shared_quick_event(session, token)


@router.get("")
def list_events(
    actor: ActorDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> Page[QuickEventSummary]:
    items, next_cursor = quick_events.list_quick_events(session, actor, limit=limit, cursor=cursor)
    return Page[QuickEventSummary](items=items, next_cursor=next_cursor)


@router.put("/{event_id}")
def save_event(
    event_id: UUID,
    data: QuickEventIn,
    actor: ActorDep,
    session: SessionDep,
    if_match: IfMatchDep,
    response: Response,
) -> QuickEventRead:
    result, created = quick_events.save_quick_event(session, actor, event_id, data, if_match)
    response.status_code = 201 if created else 200
    response.headers.update(etag(result.version))
    return result


@router.get("/{event_id}")
def get_event(
    event_id: UUID, actor: ActorDep, session: SessionDep, response: Response
) -> QuickEventRead:
    result = quick_events.get_quick_event(session, actor, event_id)
    response.headers.update(etag(result.version))
    return result


@router.delete("/{event_id}", status_code=204)
def delete_event(
    event_id: UUID, actor: ActorDep, session: SessionDep, if_match: IfMatchDep
) -> Response:
    quick_events.delete_quick_event(session, actor, event_id, if_match)
    return Response(status_code=204)


@router.post("/{event_id}/share")
def share_event(
    event_id: UUID, actor: ActorDep, session: SessionDep, settings: SettingsDep
) -> QuickShareLinkRead:
    return quick_events.share_quick_event(
        session,
        actor,
        event_id,
        base_url=settings.public_web_url,
        days=settings.quick_share_days,
    )
