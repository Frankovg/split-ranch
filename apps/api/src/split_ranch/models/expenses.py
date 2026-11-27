"""Expenses and their materialised shares."""

from datetime import date, datetime
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
from sqlalchemy.orm import Mapped, mapped_column

from split_ranch.models.base import Base, created_at_col, in_check, updated_at_col, uuid_pk
from split_ranch.models.groups import SPLIT_TYPES

SPLIT_ORIGINS = ("override", "category", "group_default")
EXPENSE_SOURCES = ("manual", "ai_text", "ai_voice")


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        UniqueConstraint("id", "group_id"),
        ForeignKeyConstraint(
            ["payer_member_id", "group_id"],
            ["group_members.id", "group_members.group_id"],
        ),
        ForeignKeyConstraint(["category_id", "group_id"], ["categories.id", "categories.group_id"]),
        CheckConstraint("amount_cents > 0 AND amount_cents <= 100000000", name="amount"),
        CheckConstraint("char_length(description) BETWEEN 1 AND 140", name="description_length"),
        CheckConstraint(in_check("split_type", SPLIT_TYPES), name="split_type"),
        CheckConstraint(in_check("split_origin", SPLIT_ORIGINS), name="split_origin"),
        CheckConstraint(in_check("participant_mode", ("all", "subset")), name="participant_mode"),
        CheckConstraint(in_check("source", EXPENSE_SOURCES), name="source"),
        # Keyset pagination and date-range filters (`expense_date` in the group time zone).
        Index("ix_expenses_group_date_id", "group_id", text("expense_date DESC"), text("id DESC")),
    )

    id: Mapped[UUID] = uuid_pk()
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    category_id: Mapped[UUID | None] = mapped_column()
    payer_member_id: Mapped[UUID] = mapped_column()
    # Euro cents; the app only handles EUR.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str] = mapped_column(String(140))
    notes: Mapped[str | None] = mapped_column(Text)
    expense_date: Mapped[date] = mapped_column(Date)
    split_type: Mapped[str] = mapped_column(String(16))
    split_origin: Mapped[str] = mapped_column(String(24))
    participant_mode: Mapped[str] = mapped_column(String(8), server_default="all", default="all")
    rule_fallback: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False
    )
    source: Mapped[str] = mapped_column(String(16), server_default="manual", default="manual")
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
            ["expense_id", "group_id"],
            ["expenses.id", "expenses.group_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["member_id", "group_id"],
            ["group_members.id", "group_members.group_id"],
        ),
        Index("ix_expense_shares_member", "group_id", "member_id"),
    )

    expense_id: Mapped[UUID] = mapped_column(primary_key=True)
    member_id: Mapped[UUID] = mapped_column(primary_key=True)
    group_id: Mapped[UUID] = mapped_column()
    sort_key: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    weight: Mapped[int | None] = mapped_column(Integer)
    basis_points: Mapped[int | None] = mapped_column(Integer)
    exact_cents: Mapped[int | None] = mapped_column(BigInteger)
