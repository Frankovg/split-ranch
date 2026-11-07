"""Periods, expenses, shares and revisions."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from split_ranch.models.base import Base, created_at_col, in_check, updated_at_col, uuid_pk
from split_ranch.models.households import SPLIT_TYPES

PERIOD_STATUSES = ("open", "closed", "settled")
SPLIT_ORIGINS = ("override", "category", "recurring", "household_default")
EXPENSE_SOURCES = ("manual", "ai_text", "ai_voice", "recurring", "adjustment")
REVISION_ACTIONS = ("create", "update", "delete", "restore", "confirm")


class Period(Base):
    __tablename__ = "periods"
    __table_args__ = (
        UniqueConstraint("household_id", "month"),
        UniqueConstraint("id", "household_id"),
        CheckConstraint(in_check("status", PERIOD_STATUSES), name="status"),
        CheckConstraint("extract(day from month) = 1", name="month_first_day"),
        Index("ix_periods_status_closes_at", "status", "closes_at"),
    )

    id: Mapped[UUID] = uuid_pk()
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"))
    month: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), server_default="open", default="open")
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # NULL = closed by the system (auto-close job).
    closed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_count: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    version: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        UniqueConstraint("id", "household_id"),
        ForeignKeyConstraint(["period_id", "household_id"], ["periods.id", "periods.household_id"]),
        ForeignKeyConstraint(
            ["payer_member_id", "household_id"],
            ["household_members.id", "household_members.household_id"],
        ),
        ForeignKeyConstraint(
            ["category_id", "household_id"], ["categories.id", "categories.household_id"]
        ),
        ForeignKeyConstraint(
            ["adjusts_expense_id", "household_id"], ["expenses.id", "expenses.household_id"]
        ),
        CheckConstraint(
            "amount_cents <> 0 AND (amount_cents > 0 OR source = 'adjustment')"
            " AND abs(amount_cents) <= 100000000",
            name="amount",
        ),
        CheckConstraint("currency = 'EUR'", name="currency_eur"),
        CheckConstraint("char_length(description) BETWEEN 1 AND 140", name="description_length"),
        CheckConstraint(in_check("split_type", SPLIT_TYPES), name="split_type"),
        CheckConstraint(in_check("split_origin", SPLIT_ORIGINS), name="split_origin"),
        CheckConstraint(in_check("participant_mode", ("all", "subset")), name="participant_mode"),
        CheckConstraint(in_check("status", ("draft", "confirmed")), name="status"),
        CheckConstraint(in_check("source", EXPENSE_SOURCES), name="source"),
        CheckConstraint(
            "source <> 'adjustment' OR adjusts_expense_id IS NOT NULL", name="adjustment_link"
        ),
        Index(
            "ix_expenses_household_period_live",
            "household_id",
            "period_id",
            postgresql_where=text("deleted_at IS NULL AND status = 'confirmed'"),
        ),
        Index(
            "ix_expenses_household_date_id",
            "household_id",
            text("expense_date DESC"),
            text("id DESC"),
        ),
    )

    id: Mapped[UUID] = uuid_pk()
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"))
    period_id: Mapped[UUID] = mapped_column()
    category_id: Mapped[UUID | None] = mapped_column()
    payer_member_id: Mapped[UUID] = mapped_column()
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), server_default="EUR", default="EUR")
    description: Mapped[str] = mapped_column(String(140))
    notes: Mapped[str | None] = mapped_column(Text)
    expense_date: Mapped[date] = mapped_column(Date)
    split_type: Mapped[str] = mapped_column(String(16))
    split_origin: Mapped[str] = mapped_column(String(24))
    participant_mode: Mapped[str] = mapped_column(String(8), server_default="all", default="all")
    rule_fallback: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False
    )
    status: Mapped[str] = mapped_column(String(16), server_default="confirmed", default="confirmed")
    source: Mapped[str] = mapped_column(String(16), server_default="manual", default="manual")
    source_transcript: Mapped[str | None] = mapped_column(Text)
    adjusts_expense_id: Mapped[UUID | None] = mapped_column()
    recurring_expense_id: Mapped[UUID | None] = mapped_column()
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_reason: Mapped[str | None] = mapped_column(String(280))


class ExpenseShare(Base):
    """Materialised shares. A deferred trigger enforces SUM(amount_cents) = expense amount."""

    __tablename__ = "expense_shares"
    __table_args__ = (
        ForeignKeyConstraint(
            ["expense_id", "household_id"],
            ["expenses.id", "expenses.household_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["member_id", "household_id"],
            ["household_members.id", "household_members.household_id"],
        ),
        Index("ix_expense_shares_member", "household_id", "member_id"),
    )

    expense_id: Mapped[UUID] = mapped_column(primary_key=True)
    member_id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID] = mapped_column()
    sort_key: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    # Sign must match the expense amount (negative only for adjustment reversals).
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    weight: Mapped[int | None] = mapped_column(Integer)
    basis_points: Mapped[int | None] = mapped_column(Integer)
    exact_cents: Mapped[int | None] = mapped_column(BigInteger)


class ExpenseRevision(Base):
    """Append-only history of an expense."""

    __tablename__ = "expense_revisions"
    __table_args__ = (
        UniqueConstraint("expense_id", "version"),
        ForeignKeyConstraint(
            ["expense_id", "household_id"],
            ["expenses.id", "expenses.household_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(in_check("action", REVISION_ACTIONS), name="action"),
    )

    id: Mapped[UUID] = uuid_pk()
    expense_id: Mapped[UUID] = mapped_column()
    household_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(String(280))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()
