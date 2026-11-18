"""Payments between members, recorded outside the app (Bizum, cash, bank transfer...).

A debtor records a payment as `sent`; it counts in the balance only once the creditor
confirms it. A creditor may record cash received directly as `confirmed`.
"""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from split_ranch.models.base import Base, created_at_col, in_check, updated_at_col, uuid_pk

PAYMENT_STATUSES = ("sent", "confirmed", "disputed", "cancelled")
# How the money moved. NULL only on payments recorded before migration 0007.
PAYMENT_METHODS = ("bizum", "bank_transfer", "cash", "other")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["from_member_id", "group_id"],
            ["group_members.id", "group_members.group_id"],
        ),
        ForeignKeyConstraint(
            ["to_member_id", "group_id"],
            ["group_members.id", "group_members.group_id"],
        ),
        CheckConstraint("amount_cents > 0 AND amount_cents <= 100000000", name="amount"),
        CheckConstraint("from_member_id <> to_member_id", name="distinct_members"),
        CheckConstraint(in_check("status", PAYMENT_STATUSES), name="status"),
        CheckConstraint(in_check("method", PAYMENT_METHODS), name="method"),
        Index("ix_payments_group_created", "group_id", text("created_at DESC"), text("id DESC")),
    )

    # Client-generated (UUIDv7): retrying a create returns the stored payment.
    id: Mapped[UUID] = uuid_pk()
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    from_member_id: Mapped[UUID] = mapped_column()
    to_member_id: Mapped[UUID] = mapped_column()
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16))
    method: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(280))
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
