"""Households, members and categories. Split rules are JSON on households/categories."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from split_ranch.models.base import Base, created_at_col, in_check, updated_at_col, uuid_pk

SPLIT_TYPES = ("equal", "weights", "percentages", "exact", "single", "personal")

# A split rule is stored as the API's `SplitSpec` JSON, e.g.
# {"split_type": "weights", "shares": [{"member_id": "...", "weight": 60}, ...]}.
DEFAULT_SPLIT_RULE: dict[str, Any] = {"split_type": "equal"}


class Household(Base):
    __tablename__ = "households"
    __table_args__ = (
        CheckConstraint("char_length(name) BETWEEN 1 AND 80", name="name_length"),
        CheckConstraint(
            "invite_code IS NULL OR char_length(invite_code) = 8", name="invite_code_length"
        ),
    )

    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(
        String(64), server_default="Europe/Madrid", default="Europe/Madrid"
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    # The household's split rule when no category rule applies.
    split_rule: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        server_default=text("""'{"split_type": "equal"}'::jsonb"""),
        default=lambda: dict(DEFAULT_SPLIT_RULE),
    )
    # One shareable join code per household (regenerated when it expires or is revoked).
    invite_code: Mapped[str | None] = mapped_column(String(8), unique=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HouseholdMember(Base):
    """Expenses reference `member_id`, not `user_id`, so history survives leaving."""

    __tablename__ = "household_members"
    __table_args__ = (
        UniqueConstraint("household_id", "user_id"),
        UniqueConstraint("id", "household_id"),
        CheckConstraint(in_check("role", ("admin", "member")), name="role"),
        CheckConstraint(in_check("status", ("active", "leaving", "left")), name="status"),
        CheckConstraint("joined_period_seq >= 1", name="joined_period_seq_positive"),
        CheckConstraint(
            "left_period_seq IS NULL OR left_period_seq >= joined_period_seq",
            name="left_after_joined",
        ),
        Index(
            "ix_household_members_active",
            "household_id",
            postgresql_where=text("status <> 'left'"),
        ),
    )

    id: Mapped[UUID] = uuid_pk()
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), server_default="member", default="member")
    status: Mapped[str] = mapped_column(String(16), server_default="active", default="active")
    sort_key: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    # Period sequence numbers (`Period.seq`): the member takes part in every period from
    # `joined_period_seq` to `left_period_seq`, both included (NULL = still a member).
    joined_period_seq: Mapped[int] = mapped_column(Integer)
    left_period_seq: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("id", "household_id"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 40", name="name_length"),
        Index(
            "uq_categories_household_name",
            "household_id",
            func.lower(text("name")),
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = uuid_pk()
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(40))
    icon: Mapped[str | None] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(16))
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_key: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    # Overrides the household rule for this category's expenses (NULL = no override).
    split_rule: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


__all__ = [
    "DEFAULT_SPLIT_RULE",
    "SPLIT_TYPES",
    "Category",
    "Household",
    "HouseholdMember",
]
