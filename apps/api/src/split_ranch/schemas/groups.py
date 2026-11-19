"""Users, groups, members, invitation code and categories."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from split_ranch.schemas.common import Id, ReadModel, StrictModel
from split_ranch.schemas.notifications import NotificationPrefs, NotificationPrefsUpdate

Role = Literal["admin", "member"]


# ------------------------------------------------------------------ users


class MembershipRead(ReadModel):
    group_id: Id
    group_name: str
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
    notifications: NotificationPrefs


class MeUpdate(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    notifications: NotificationPrefsUpdate | None = None


# ------------------------------------------------------------- groups


class GroupCreate(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    timezone: str = Field(default="Europe/Madrid", max_length=64)


class GroupUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    timezone: str | None = Field(default=None, max_length=64)


class MemberRead(ReadModel):
    id: Id
    user_id: Id
    display_name: str | None
    role: str
    status: str
    sort_key: int
    joined_at: datetime
    left_at: datetime | None


class GroupRead(ReadModel):
    id: Id
    name: str
    timezone: str
    created_at: datetime
    members: list[MemberRead]
    my_member_id: Id
    my_role: str


class GroupDeleteIn(StrictModel):
    # The admin types the group's name to confirm.
    confirm_name: str = Field(min_length=1, max_length=80)


# ------------------------------------------------------------ invitations


class InvitationRead(ReadModel):
    """The group's join code (one per group, valid 7 days), typed by hand by the invitee."""

    code: str
    expires_at: datetime


class InvitationPreview(ReadModel):
    group_name: str
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


# ------------------------------------------------------- category presets


class CategoryPresetCreate(StrictModel):
    """New expenses whose description contains `keyword` get `category_id`."""

    keyword: str = Field(min_length=1, max_length=40)
    category_id: Id


class CategoryPresetRead(ReadModel):
    id: Id
    keyword: str
    category_id: Id
    created_at: datetime
