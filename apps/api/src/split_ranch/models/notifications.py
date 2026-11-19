"""Push notification device tokens."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from split_ranch.models.base import Base, created_at_col, in_check, updated_at_col, uuid_pk

PUSH_PLATFORMS = ("android", "ios")


class PushToken(Base):
    """One Expo push token per device; re-registering moves it to the signed-in user."""

    __tablename__ = "push_tokens"
    __table_args__ = (
        CheckConstraint("token ~ '^Expo(nent)?PushToken\\[.+\\]$'", name="token_format"),
        CheckConstraint(in_check("platform", PUSH_PLATFORMS), name="platform"),
    )

    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True)
    platform: Mapped[str] = mapped_column(String(16))
    # Language of the app on this device ('es' or 'en'): the notification text uses it.
    locale: Mapped[str] = mapped_column(String(8), server_default="es", default="es")
    # Latest push ticket whose receipt has not been checked yet (see use_cases.notifications).
    last_ticket_id: Mapped[str | None] = mapped_column(String(64))
    last_ticket_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
