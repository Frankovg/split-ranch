"""Users, households, members, invitations and categories."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from split_ranch.schemas.common import Id, ReadModel, StrictModel

Role = Literal["admin", "member"]
StartPeriod = Literal["current", "next"]


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
    payment_handles: dict[str, Any]


class MeRead(UserRead):
    memberships: list[MembershipRead]


class PaymentHandles(StrictModel):
    bizum_phone: str | None = Field(default=None, max_length=20, pattern=r"^\+?[0-9 ]{6,20}$")
    paypal_me: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    revolut: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")


class MeUpdate(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    payment_handles: PaymentHandles | None = None


class PushTokenIn(StrictModel):
    expo_token: str = Field(min_length=10, max_length=255)
    platform: Literal["android", "ios"]


# ------------------------------------------------------------- households


class HouseholdCreate(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    timezone: str = Field(default="Europe/Madrid", max_length=64)


class HouseholdUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    grace_days: int | None = Field(default=None, ge=0, le=15)
    auto_close: bool | None = None
    timezone: str | None = Field(default=None, max_length=64)


class MemberRead(ReadModel):
    id: Id
    user_id: Id
    display_name: str | None
    role: str
    status: str
    sort_key: int
    joined_period: date
    left_period: date | None


class HouseholdRead(ReadModel):
    id: Id
    name: str
    timezone: str
    currency: str
    grace_days: int
    auto_close: bool
    version: int
    created_at: datetime
    members: list[MemberRead]
    my_member_id: Id
    my_role: str


class MemberRoleUpdate(StrictModel):
    role: Role


# ------------------------------------------------------------ invitations


class InvitationCreate(StrictModel):
    expires_in_days: int = Field(default=7, ge=1, le=30)
    max_uses: int = Field(default=5, ge=1, le=50)
    start_period: StartPeriod | None = None


class InvitationRead(ReadModel):
    id: Id
    code: str
    url: str
    expires_at: datetime
    max_uses: int
    uses: int
    start_period: str | None


class InvitationPreview(ReadModel):
    household_name: str
    inviter: str | None
    member_count: int
    expires_at: datetime


class InvitationAccept(StrictModel):
    start_period: StartPeriod | None = None


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
