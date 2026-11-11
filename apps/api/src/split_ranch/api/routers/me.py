"""Current user."""

from fastapi import APIRouter

from split_ranch.api.deps import ActorDep, SessionDep
from split_ranch.schemas.households import MeRead, MeUpdate
from split_ranch.use_cases import users

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
def get_me(actor: ActorDep, session: SessionDep) -> MeRead:
    return users.get_me(session, actor)


@router.patch("")
def update_me(data: MeUpdate, actor: ActorDep, session: SessionDep) -> MeRead:
    return users.update_profile(session, actor, data)
