"""Push tokens and notification preferences."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from split_ranch.schemas.common import ReadModel, StrictModel

# An Expo push token, not a secret credential.
TOKEN_PATTERN = r"^Expo(nent)?PushToken\[.+\]$"  # noqa: S105


class NotificationPrefs(ReadModel):
    """In-app switches. `enabled` is the master switch; the rest are per event type."""

    enabled: bool = True
    expense_created: bool = True
    # Edits and deletions of expenses the user takes part in.
    expense_changed: bool = True
    payments: bool = True
    member_joined: bool = True


class NotificationPrefsUpdate(StrictModel):
    """Partial update: only the fields sent change."""

    enabled: bool | None = None
    expense_created: bool | None = None
    expense_changed: bool | None = None
    payments: bool | None = None
    member_joined: bool | None = None


class PushTokenIn(StrictModel):
    token: str = Field(min_length=1, max_length=255, pattern=TOKEN_PATTERN)
    platform: Literal["android", "ios"]
    # App language on this device; the notification text uses it.
    locale: Literal["es", "en"] = "es"


class PushTokenDelete(StrictModel):
    token: str = Field(min_length=1, max_length=255, pattern=TOKEN_PATTERN)
