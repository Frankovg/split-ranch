"""Current user: profile, notification switches, this device's push token, deletion."""

from fastapi import APIRouter, Request, Response

from split_ranch.api.deps import ActorDep, SessionDep
from split_ranch.schemas.groups import MeDeleteIn, MeRead, MeUpdate
from split_ranch.schemas.notifications import PushTokenDelete, PushTokenIn
from split_ranch.use_cases import account, notifications, users

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
def get_me(actor: ActorDep, session: SessionDep) -> MeRead:
    return users.get_me(session, actor)


@router.patch("")
def update_me(data: MeUpdate, actor: ActorDep, session: SessionDep) -> MeRead:
    """Profile and notification switches (`notifications` is a partial update)."""
    return users.update_profile(session, actor, data)


@router.delete("", status_code=204)
def delete_me(data: MeDeleteIn, request: Request, actor: ActorDep, session: SessionDep) -> Response:
    """Delete the account: needs every group settled (`409 account_has_open_balances`)."""
    account.delete_account(session, actor, request.app.state.auth_admin)
    return Response(status_code=204)


@router.put("/push-tokens", status_code=204)
def register_push_token(data: PushTokenIn, actor: ActorDep, session: SessionDep) -> Response:
    """Register (or refresh) this device's Expo push token for the signed-in user."""
    notifications.register_token(session, actor, data)
    return Response(status_code=204)


@router.delete("/push-tokens", status_code=204)
def unregister_push_token(data: PushTokenDelete, actor: ActorDep, session: SessionDep) -> Response:
    """Stop sending to this device (sign-out). Unknown tokens are ignored."""
    notifications.unregister_token(session, actor, data)
    return Response(status_code=204)
