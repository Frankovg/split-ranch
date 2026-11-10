"""Settlement snapshots and transfers."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from split_ranch.models.base import Base, created_at_col, in_check, updated_at_col, uuid_pk

TRANSFER_STATUSES = ("pending", "sent", "confirmed", "disputed", "cancelled")
SNAPSHOT_TRIGGERS = ("close", "edit_after_close", "reopen_close")


class SettlementSnapshot(Base):
    """Immutable; the latest non-superseded snapshot of a period is the current one."""

    __tablename__ = "settlement_snapshots"
    __table_args__ = (
        UniqueConstraint("period_id", "seq"),
        UniqueConstraint("id", "household_id"),
        ForeignKeyConstraint(
            ["period_id", "household_id"],
            ["periods.id", "periods.household_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(in_check("trigger", SNAPSHOT_TRIGGERS), name="trigger"),
        CheckConstraint("seq >= 1", name="seq_positive"),
    )

    id: Mapped[UUID] = uuid_pk()
    household_id: Mapped[UUID] = mapped_column()
    period_id: Mapped[UUID] = mapped_column()
    seq: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(String(24))
    balances: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    transfers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    input_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_col()
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SettlementTransfer(Base):
    __tablename__ = "settlement_transfers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["period_id", "household_id"],
            ["periods.id", "periods.household_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "household_id"],
            ["settlement_snapshots.id", "settlement_snapshots.household_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["from_member_id", "household_id"],
            ["household_members.id", "household_members.household_id"],
        ),
        ForeignKeyConstraint(
            ["to_member_id", "household_id"],
            ["household_members.id", "household_members.household_id"],
        ),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        CheckConstraint("from_member_id <> to_member_id", name="distinct_members"),
        CheckConstraint(in_check("status", TRANSFER_STATUSES), name="status"),
    )

    id: Mapped[UUID] = uuid_pk()
    household_id: Mapped[UUID] = mapped_column(index=True)
    period_id: Mapped[UUID] = mapped_column(index=True)
    snapshot_id: Mapped[UUID] = mapped_column()
    from_member_id: Mapped[UUID] = mapped_column()
    to_member_id: Mapped[UUID] = mapped_column()
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), server_default="pending", default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(String(280))
    version: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
