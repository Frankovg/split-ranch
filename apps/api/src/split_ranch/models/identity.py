"""Users."""

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from split_ranch.models.base import Base, created_at_col, updated_at_col

NOTIFICATION_PREF_KEYS = (
    "enabled",
    "expense_created",
    "expense_changed",
    "payments",
    "member_joined",
)
DEFAULT_NOTIFICATION_PREFS: dict[str, bool] = dict.fromkeys(NOTIFICATION_PREF_KEYS, True)
DEFAULT_NOTIFICATION_PREFS_JSON = json.dumps(DEFAULT_NOTIFICATION_PREFS)


class User(Base):
    """`id` equals the Supabase `auth.users.id` (JWT `sub`); no FK into `auth`."""

    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_email_lower",
            func.lower(text("email")),
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND email IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(String(16), server_default="es-ES", default="es-ES")
    # In-app notification switches; keys in NOTIFICATION_PREF_KEYS, all on by default.
    notification_prefs: Mapped[dict[str, bool]] = mapped_column(
        JSONB,
        server_default=text(f"'{DEFAULT_NOTIFICATION_PREFS_JSON}'::jsonb"),
        default=lambda: dict(DEFAULT_NOTIFICATION_PREFS),
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
