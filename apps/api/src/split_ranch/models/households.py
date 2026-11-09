"""Households, members, invitations, categories and split rules."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from split_ranch.models.base import Base, created_at_col, in_check, updated_at_col, uuid_pk

SPLIT_TYPES = ("equal", "weights", "percentages", "exact", "single", "personal")


class Household(Base):
    __tablename__ = "households"
    __table_args__ = (
        CheckConstraint("currency = 'EUR'", name="currency_eur"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 80", name="name_length"),
    )

    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(
        String(64), server_default="Europe/Madrid", default="Europe/Madrid"
    )
    currency: Mapped[str] = mapped_column(String(3), server_default="EUR", default="EUR")
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
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
    display_name_override: Mapped[str | None] = mapped_column(String(80))
    sort_key: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    # Period sequence numbers (`Period.seq`): the member takes part in every period from
    # `joined_period_seq` to `left_period_seq`, both included (NULL = still a member).
    joined_period_seq: Mapped[int] = mapped_column(Integer)
    left_period_seq: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint("max_uses BETWEEN 1 AND 50", name="max_uses_range"),
        CheckConstraint("uses >= 0 AND uses <= max_uses", name="uses_range"),
        CheckConstraint(
            "start_period IS NULL OR " + in_check("start_period", ("current", "next")),
            name="start_period",
        ),
        CheckConstraint("char_length(code) = 8", name="code_length"),
    )

    id: Mapped[UUID] = uuid_pk()
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(8), unique=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_col()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_uses: Mapped[int] = mapped_column(Integer, server_default="5", default=5)
    uses: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 'current' = the open period, 'next' = the next period started. NULL = 'current'.
    start_period: Mapped[str | None] = mapped_column(String(8))


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
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class SplitRule(Base):
    __tablename__ = "split_rules"
    __table_args__ = (
        UniqueConstraint("id", "household_id"),
        CheckConstraint(
            in_check("scope", ("household_default", "category", "recurring")), name="scope"
        ),
        CheckConstraint(in_check("split_type", SPLIT_TYPES), name="split_type"),
        CheckConstraint("(scope = 'category') = (category_id IS NOT NULL)", name="category_scope"),
        CheckConstraint(
            "(scope = 'recurring') = (recurring_expense_id IS NOT NULL)", name="recurring_scope"
        ),
        ForeignKeyConstraint(
            ["category_id", "household_id"],
            ["categories.id", "categories.household_id"],
            ondelete="CASCADE",
        ),
        Index(
            "uq_split_rules_household_default",
            "household_id",
            unique=True,
            postgresql_where=text("scope = 'household_default'"),
        ),
        Index(
            "uq_split_rules_category",
            "category_id",
            unique=True,
            postgresql_where=text("scope = 'category'"),
        ),
        Index(
            "uq_split_rules_recurring",
            "recurring_expense_id",
            unique=True,
            postgresql_where=text("scope = 'recurring'"),
        ),
    )

    id: Mapped[UUID] = uuid_pk()
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(24))
    category_id: Mapped[UUID | None] = mapped_column()
    # recurring_expenses is a post-MVP table: no FK yet.
    recurring_expense_id: Mapped[UUID | None] = mapped_column()
    split_type: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class SplitRuleShare(Base):
    __tablename__ = "split_rule_shares"
    __table_args__ = (
        ForeignKeyConstraint(
            ["split_rule_id", "household_id"],
            ["split_rules.id", "split_rules.household_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["member_id", "household_id"],
            ["household_members.id", "household_members.household_id"],
        ),
        CheckConstraint("weight IS NULL OR weight >= 0", name="weight_non_negative"),
        CheckConstraint(
            "basis_points IS NULL OR basis_points BETWEEN 0 AND 10000", name="basis_points_range"
        ),
        CheckConstraint("amount_cents IS NULL OR amount_cents >= 0", name="amount_non_negative"),
    )

    split_rule_id: Mapped[UUID] = mapped_column(primary_key=True)
    member_id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID] = mapped_column()
    sort_key: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    weight: Mapped[int | None] = mapped_column(Integer)
    basis_points: Mapped[int | None] = mapped_column(Integer)
    amount_cents: Mapped[int | None] = mapped_column(BigInteger)


__all__ = [
    "SPLIT_TYPES",
    "Category",
    "Household",
    "HouseholdMember",
    "Invitation",
    "SplitRule",
    "SplitRuleShare",
]
