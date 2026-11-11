"""Users, households, members, invitation code and categories."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from split_ranch.schemas.common import Id, ReadModel, StrictModel

Role = Literal["admin", "member"]


# ------------------------------------------------------------------ users


class MembershipRead(ReadModel):
    household_id: Id
    household_name: str
    member_id: Id
    role: str
    status: str


class UserRead(ReadModel):
    id: Id
    email: str | None
    display_name: str | None
    avatar_url: str | None
    locale: str


class MeRead(UserRead):
    memberships: list[MembershipRead]


class MeUpdate(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")


# ------------------------------------------------------------- households


class HouseholdCreate(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    timezone: str = Field(default="Europe/Madrid", max_length=64)


class HouseholdUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    timezone: str | None = Field(default=None, max_length=64)


class MemberRead(ReadModel):
    id: Id
    user_id: Id
    display_name: str | None
    role: str
    status: str
    sort_key: int
    joined_period_seq: int
    left_period_seq: int | None


class HouseholdRead(ReadModel):
    id: Id
    name: str
    timezone: str
    created_at: datetime
    members: list[MemberRead]
    my_member_id: Id
    my_role: str


class MemberRoleUpdate(StrictModel):
    role: Role


# ------------------------------------------------------------ invitations


class InvitationRead(ReadModel):
    """The household's join code (one per household, valid 7 days)."""

    code: str
    url: str
    expires_at: datetime


class InvitationPreview(ReadModel):
    household_name: str
    member_count: int
    expires_at: datetime


# ------------------------------------------------------------- categories


class CategoryCreate(StrictModel):
    name: str = Field(min_length=1, max_length=40)
    icon: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    sort_key: int | None = Field(default=None, ge=0, le=10_000)


class CategoryUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    icon: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    sort_key: int | None = Field(default=None, ge=0, le=10_000)


class CategoryRead(ReadModel):
    id: Id
    name: str
    icon: str | None
    color: str | None
    is_default: bool
    sort_key: int
    archived_at: datetime | None
