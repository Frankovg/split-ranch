"""Groups, members and categories. Split rules are JSON on groups/categories."""

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


class Group(Base):
    __tablename__ = "groups"
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
    # The group's split rule when no category rule applies.
    split_rule: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        server_default=text("""'{"split_type": "equal"}'::jsonb"""),
        default=lambda: dict(DEFAULT_SPLIT_RULE),
    )
    # One shareable join code per group (regenerated when it expires or is revoked).
    invite_code: Mapped[str | None] = mapped_column(String(8), unique=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GroupMember(Base):
    """Expenses reference `member_id`, not `user_id`, so history survives leaving."""

    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id"),
        UniqueConstraint("id", "group_id"),
        CheckConstraint(in_check("role", ("admin", "member")), name="role"),
        CheckConstraint(in_check("status", ("active", "left")), name="status"),
        CheckConstraint("left_at IS NULL OR left_at >= joined_at", name="left_after_joined"),
        Index(
            "ix_group_members_active",
            "group_id",
            postgresql_where=text("status <> 'left'"),
        ),
        # Exactly one admin among the active members (the role passes on when they leave).
        Index(
            "uq_group_members_one_admin",
            "group_id",
            unique=True,
            postgresql_where=text("role = 'admin' AND status = 'active'"),
        ),
    )

    id: Mapped[UUID] = uuid_pk()
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), server_default="member", default="member")
    status: Mapped[str] = mapped_column(String(16), server_default="active", default="active")
    sort_key: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    # When the member (last) joined and left; NULL `left_at` = still a member.
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("id", "group_id"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 40", name="name_length"),
        Index(
            "uq_categories_group_name",
            "group_id",
            func.lower(text("name")),
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = uuid_pk()
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(40))
    icon: Mapped[str | None] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(16))
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_key: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    # Overrides the group rule for this category's expenses (NULL = no override).
    split_rule: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


__all__ = [
    "DEFAULT_SPLIT_RULE",
    "SPLIT_TYPES",
    "Category",
    "Group",
    "GroupMember",
]
