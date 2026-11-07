"""Households, invitations, members, categories and split rules."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Response

from split_ranch.api.deps import (
    ActorDep,
    HouseholdActorDep,
    IfMatchDep,
    SessionDep,
    SettingsDep,
    etag,
)
from split_ranch.schemas.households import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    HouseholdCreate,
    HouseholdRead,
    HouseholdUpdate,
    InvitationAccept,
    InvitationCreate,
    InvitationPreview,
    InvitationRead,
    MemberRoleUpdate,
)
from split_ranch.schemas.split import SplitRuleRead, SplitRulesRead, SplitSpec
from split_ranch.use_cases import households, rules

router = APIRouter(tags=["households"])


@router.post("/households", status_code=201)
def create_household(
    data: HouseholdCreate, actor: ActorDep, session: SessionDep, response: Response
) -> HouseholdRead:
    result = households.create_household(session, actor, data)
    response.headers.update(etag(result.version))
    return result


@router.get("/households/{household_id}")
def get_household(
    actor: HouseholdActorDep, session: SessionDep, response: Response
) -> HouseholdRead:
    result = households.get_household(session, actor)
    response.headers.update(etag(result.version))
    return result


@router.patch("/households/{household_id}")
def update_household(
    data: HouseholdUpdate,
    actor: HouseholdActorDep,
    session: SessionDep,
    if_match: IfMatchDep,
    response: Response,
) -> HouseholdRead:
    result = households.update_household(session, actor, data, if_match)
    response.headers.update(etag(result.version))
    return result


# ------------------------------------------------------------ invitations


@router.post("/households/{household_id}/invitations", status_code=201)
def create_invitation(
    actor: HouseholdActorDep,
    session: SessionDep,
    settings: SettingsDep,
    data: Annotated[InvitationCreate | None, Body()] = None,
) -> InvitationRead:
    return households.create_invitation(
        session, actor, data or InvitationCreate(), base_url=settings.public_web_url
    )


@router.delete("/households/{household_id}/invitations/{invitation_id}", status_code=204)
def revoke_invitation(
    invitation_id: UUID, actor: HouseholdActorDep, session: SessionDep
) -> Response:
    households.revoke_invitation(session, actor, invitation_id)
    return Response(status_code=204)


@router.get("/invitations/{code}")
def preview_invitation(code: str, actor: ActorDep, session: SessionDep) -> InvitationPreview:
    return households.preview_invitation(session, actor, code)


@router.post("/invitations/{code}/accept")
def accept_invitation(
    code: str,
    actor: ActorDep,
    session: SessionDep,
    data: Annotated[InvitationAccept | None, Body()] = None,
) -> HouseholdRead:
    return households.accept_invitation(session, actor, code, data or InvitationAccept())


# ---------------------------------------------------------------- members


@router.post("/households/{household_id}/members/me/leave")
def leave_household(actor: HouseholdActorDep, session: SessionDep) -> HouseholdRead:
    return households.leave_household(session, actor)


@router.patch("/households/{household_id}/members/{member_id}")
def change_member_role(
    member_id: UUID, data: MemberRoleUpdate, actor: HouseholdActorDep, session: SessionDep
) -> HouseholdRead:
    return households.change_member_role(session, actor, member_id, data)


@router.delete("/households/{household_id}/members/{member_id}")
def remove_member(member_id: UUID, actor: HouseholdActorDep, session: SessionDep) -> HouseholdRead:
    return households.remove_member(session, actor, member_id)


# ------------------------------------------------------------- categories


@router.get("/households/{household_id}/categories")
def list_categories(
    actor: HouseholdActorDep, session: SessionDep, include_archived: bool = False
) -> list[CategoryRead]:
    return rules.list_categories(session, actor, include_archived=include_archived)


@router.post("/households/{household_id}/categories", status_code=201)
def create_category(
    data: CategoryCreate, actor: HouseholdActorDep, session: SessionDep
) -> CategoryRead:
    return rules.create_category(session, actor, data)


@router.patch("/households/{household_id}/categories/{category_id}")
def update_category(
    category_id: UUID, data: CategoryUpdate, actor: HouseholdActorDep, session: SessionDep
) -> CategoryRead:
    return rules.update_category(session, actor, category_id, data)


@router.delete("/households/{household_id}/categories/{category_id}", status_code=204)
def archive_category(category_id: UUID, actor: HouseholdActorDep, session: SessionDep) -> Response:
    rules.archive_category(session, actor, category_id)
    return Response(status_code=204)


# ------------------------------------------------------------ split rules


@router.get("/households/{household_id}/split-rules")
def list_split_rules(actor: HouseholdActorDep, session: SessionDep) -> SplitRulesRead:
    return rules.list_rules(session, actor)


@router.put("/households/{household_id}/split-rules/default")
def set_default_rule(
    spec: Annotated[SplitSpec, Body()], actor: HouseholdActorDep, session: SessionDep
) -> SplitRuleRead:
    return rules.set_default_rule(session, actor, spec)


@router.put("/households/{household_id}/categories/{category_id}/split-rule")
def set_category_rule(
    category_id: UUID,
    spec: Annotated[SplitSpec, Body()],
    actor: HouseholdActorDep,
    session: SessionDep,
) -> SplitRuleRead:
    return rules.set_category_rule(session, actor, category_id, spec)


@router.delete("/households/{household_id}/categories/{category_id}/split-rule", status_code=204)
def delete_category_rule(
    category_id: UUID, actor: HouseholdActorDep, session: SessionDep
) -> Response:
    rules.delete_category_rule(session, actor, category_id)
    return Response(status_code=204)
