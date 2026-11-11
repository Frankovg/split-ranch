"""Users."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from split_ranch.models.base import Base, created_at_col, updated_at_col


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
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
