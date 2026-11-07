"""Quick splits: independent of households (no FK to any household table)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
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

from split_ranch.models.base import Base, created_at_col, in_check, updated_at_col


class QuickEvent(Base):
    __tablename__ = "quick_events"
    __table_args__ = (
        CheckConstraint(in_check("mode", ("total", "itemised")), name="mode"),
        CheckConstraint("currency = 'EUR'", name="currency_eur"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 80", name="title_length"),
        Index(
            "ix_quick_events_owner_live",
            "owner_user_id",
            text("updated_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(80))
    mode: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3), server_default="EUR", default="EUR")
    share_token: Mapped[str | None] = mapped_column(String(32), unique=True)
    share_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuickParticipant(Base):
    __tablename__ = "quick_participants"
    __table_args__ = (
        UniqueConstraint("id", "event_id"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 40", name="name_length"),
        CheckConstraint("weight >= 0", name="weight_non_negative"),
        Index(
            "uq_quick_participants_event_name",
            "event_id",
            func.lower(text("name")),
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("quick_events.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(40))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    sort_key: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    weight: Mapped[int] = mapped_column(Integer, server_default="1", default=1)


class QuickExpense(Base):
    __tablename__ = "quick_expenses"
    __table_args__ = (
        UniqueConstraint("id", "event_id"),
        ForeignKeyConstraint(
            ["payer_participant_id", "event_id"],
            ["quick_participants.id", "quick_participants.event_id"],
        ),
        CheckConstraint("amount_cents > 0 AND amount_cents <= 100000000", name="amount"),
        CheckConstraint(in_check("split_type", ("equal", "weights", "exact")), name="split_type"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("quick_events.id", ondelete="CASCADE"), index=True
    )
    payer_participant_id: Mapped[UUID | None] = mapped_column()
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str | None] = mapped_column(String(140))
    split_type: Mapped[str] = mapped_column(String(16))
    sort_key: Mapped[int] = mapped_column(Integer, server_default="0", default=0)


class QuickExpenseShare(Base):
    __tablename__ = "quick_expense_shares"
    __table_args__ = (
        ForeignKeyConstraint(
            ["quick_expense_id", "event_id"],
            ["quick_expenses.id", "quick_expenses.event_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["participant_id", "event_id"],
            ["quick_participants.id", "quick_participants.event_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("amount_cents >= 0", name="amount_non_negative"),
    )

    quick_expense_id: Mapped[UUID] = mapped_column(primary_key=True)
    participant_id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column()
    weight: Mapped[int | None] = mapped_column(Integer)
    exact_cents: Mapped[int | None] = mapped_column(BigInteger)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
