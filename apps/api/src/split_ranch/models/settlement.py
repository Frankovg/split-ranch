"""Settlement transfers of a period.

Closing a period computes the minimal transfers from the balances. When the period changes
afterwards (edit after close, reopen), its pending transfers become `cancelled` and new
ones are computed, so the period's live transfers are the ones not cancelled.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from split_ranch.models.base import Base, created_at_col, in_check, updated_at_col, uuid_pk

TRANSFER_STATUSES = ("pending", "sent", "confirmed", "disputed", "cancelled")


class SettlementTransfer(Base):
    __tablename__ = "settlement_transfers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["period_id", "household_id"],
            ["periods.id", "periods.household_id"],
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
