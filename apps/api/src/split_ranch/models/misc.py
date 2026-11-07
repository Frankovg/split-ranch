"""Idempotency keys, audit log and Google Sheets bookkeeping."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from split_ranch.models.base import Base, created_at_col, in_check, uuid_pk


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "key"),
        Index("ix_idempotency_keys_created_at", "created_at"),
    )

    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(64))
    endpoint: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity", "entity_id"),)

    id: Mapped[UUID] = uuid_pk()
    household_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[UUID] = mapped_column()
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40))
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class HouseholdSpreadsheet(Base):
    __tablename__ = "household_spreadsheets"

    id: Mapped[UUID] = uuid_pk()
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), unique=True
    )
    spreadsheet_id: Mapped[str] = mapped_column(String(128))
    drive_file_id: Mapped[str] = mapped_column(String(128))
    shared_with: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = created_at_col()


class SheetTab(Base):
    __tablename__ = "sheet_tabs"
    __table_args__ = (
        UniqueConstraint("period_id"),
        ForeignKeyConstraint(
            ["period_id", "household_id"],
            ["periods.id", "periods.household_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(in_check("status", ("pending", "synced", "error")), name="status"),
    )

    id: Mapped[UUID] = uuid_pk()
    household_id: Mapped[UUID] = mapped_column(index=True)
    period_id: Mapped[UUID] = mapped_column()
    sheet_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(100))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), server_default="pending", default="pending")
