"""Current user."""

from fastapi import APIRouter, Response

from split_ranch.api.deps import ActorDep, SessionDep
from split_ranch.schemas.households import MeRead, MeUpdate, PushTokenIn
from split_ranch.use_cases import users

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
def get_me(actor: ActorDep, session: SessionDep) -> MeRead:
    return users.get_me(session, actor)


@router.patch("")
def update_me(data: MeUpdate, actor: ActorDep, session: SessionDep) -> MeRead:
    return users.update_profile(session, actor, data)


@router.post("/push-tokens", status_code=204)
def register_push_token(data: PushTokenIn, actor: ActorDep, session: SessionDep) -> Response:
    users.register_push_token(session, actor, data)
    return Response(status_code=204)


@router.delete("/push-tokens/{token}", status_code=204)
def delete_push_token(token: str, actor: ActorDep, session: SessionDep) -> Response:
    users.delete_push_token(session, actor, token)
    return Response(status_code=204)
