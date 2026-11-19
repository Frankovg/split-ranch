"""Groups, invitation code, members, categories, category presets and split rules."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Response

from split_ranch.api.deps import ActorDep, GroupActorDep, SessionDep
from split_ranch.schemas.groups import (
    CategoryCreate,
    CategoryPresetCreate,
    CategoryPresetRead,
    CategoryRead,
    CategoryUpdate,
    GroupCreate,
    GroupDeleteIn,
    GroupRead,
    GroupUpdate,
    InvitationPreview,
    InvitationRead,
)
from split_ranch.schemas.split import CategoryRuleRead, SplitRulesRead, SplitSpec
from split_ranch.use_cases import groups, rules

router = APIRouter(tags=["groups"])


@router.post("/groups", status_code=201)
def create_group(data: GroupCreate, actor: ActorDep, session: SessionDep) -> GroupRead:
    return groups.create_group(session, actor, data)


@router.get("/groups")
def list_groups(actor: ActorDep, session: SessionDep) -> list[GroupRead]:
    """The caller's groups (active memberships), oldest first."""
    return groups.list_groups(session, actor)


@router.get("/groups/{group_id}")
def get_group(actor: GroupActorDep, session: SessionDep) -> GroupRead:
    return groups.get_group(session, actor)


@router.patch("/groups/{group_id}")
def update_group(data: GroupUpdate, actor: GroupActorDep, session: SessionDep) -> GroupRead:
    return groups.update_group(session, actor, data)


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(data: GroupDeleteIn, actor: GroupActorDep, session: SessionDep) -> Response:
    """Admin only; every balance must be zero (`409 group_has_open_balances`)."""
    groups.delete_group(session, actor, data)
    return Response(status_code=204)


# ------------------------------------------------------------ invitations


@router.post("/groups/{group_id}/invitations")
def get_invitation(actor: GroupActorDep, session: SessionDep) -> InvitationRead:
    """The group's join code: the current one while valid, else a new one."""
    return groups.get_or_create_invitation(session, actor)


@router.delete("/groups/{group_id}/invitations", status_code=204)
def revoke_invitation(actor: GroupActorDep, session: SessionDep) -> Response:
    groups.revoke_invitation(session, actor)
    return Response(status_code=204)


@router.get("/invitations/{code}")
def preview_invitation(code: str, actor: ActorDep, session: SessionDep) -> InvitationPreview:
    return groups.preview_invitation(session, actor, code)


@router.post("/invitations/{code}/accept")
def accept_invitation(code: str, actor: ActorDep, session: SessionDep) -> GroupRead:
    return groups.accept_invitation(session, actor, code)


# ---------------------------------------------------------------- members


@router.post("/groups/{group_id}/members/me/leave", status_code=204)
def leave_group(actor: GroupActorDep, session: SessionDep) -> Response:
    """Needs a zero balance (`409 member_has_open_balance`)."""
    groups.leave_group(session, actor)
    return Response(status_code=204)


@router.delete("/groups/{group_id}/members/{member_id}")
def remove_member(member_id: UUID, actor: GroupActorDep, session: SessionDep) -> GroupRead:
    """Admin only; the member's balance must be zero."""
    return groups.remove_member(session, actor, member_id)


# ------------------------------------------------------------- categories


@router.get("/groups/{group_id}/categories")
def list_categories(
    actor: GroupActorDep, session: SessionDep, include_archived: bool = False
) -> list[CategoryRead]:
    return rules.list_categories(session, actor, include_archived=include_archived)


@router.post("/groups/{group_id}/categories", status_code=201)
def create_category(
    data: CategoryCreate, actor: GroupActorDep, session: SessionDep
) -> CategoryRead:
    return rules.create_category(session, actor, data)


@router.patch("/groups/{group_id}/categories/{category_id}")
def update_category(
    category_id: UUID, data: CategoryUpdate, actor: GroupActorDep, session: SessionDep
) -> CategoryRead:
    return rules.update_category(session, actor, category_id, data)


@router.delete("/groups/{group_id}/categories/{category_id}", status_code=204)
def archive_category(category_id: UUID, actor: GroupActorDep, session: SessionDep) -> Response:
    rules.archive_category(session, actor, category_id)
    return Response(status_code=204)


# ------------------------------------------------------- category presets


@router.get("/groups/{group_id}/category-presets")
def list_category_presets(actor: GroupActorDep, session: SessionDep) -> list[CategoryPresetRead]:
    """Keywords that pick a category for new expenses (empty until members add some)."""
    return rules.list_category_presets(session, actor)


@router.post("/groups/{group_id}/category-presets", status_code=201)
def create_category_preset(
    data: CategoryPresetCreate, actor: GroupActorDep, session: SessionDep
) -> CategoryPresetRead:
    """`409 preset_exists` when the keyword is taken (case ignored)."""
    return rules.create_category_preset(session, actor, data)


@router.delete("/groups/{group_id}/category-presets/{preset_id}", status_code=204)
def delete_category_preset(preset_id: UUID, actor: GroupActorDep, session: SessionDep) -> Response:
    rules.delete_category_preset(session, actor, preset_id)
    return Response(status_code=204)


# ------------------------------------------------------------ split rules


@router.get("/groups/{group_id}/split-rules")
def list_split_rules(actor: GroupActorDep, session: SessionDep) -> SplitRulesRead:
    return rules.list_rules(session, actor)


@router.put("/groups/{group_id}/split-rules/default")
def set_default_rule(
    spec: Annotated[SplitSpec, Body()], actor: GroupActorDep, session: SessionDep
) -> SplitSpec:
    return rules.set_default_rule(session, actor, spec)


@router.put("/groups/{group_id}/categories/{category_id}/split-rule")
def set_category_rule(
    category_id: UUID,
    spec: Annotated[SplitSpec, Body()],
    actor: GroupActorDep,
    session: SessionDep,
) -> CategoryRuleRead:
    return rules.set_category_rule(session, actor, category_id, spec)


@router.delete("/groups/{group_id}/categories/{category_id}/split-rule", status_code=204)
def delete_category_rule(category_id: UUID, actor: GroupActorDep, session: SessionDep) -> Response:
    rules.delete_category_rule(session, actor, category_id)
    return Response(status_code=204)
