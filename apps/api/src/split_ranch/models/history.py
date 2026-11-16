"""Append-only history of every change (expenses and group events)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from split_ranch.models.base import Base, created_at_col, uuid_pk


class History(Base):
    """One row per change. A trigger rejects UPDATEs; rows go only with their group.

    Expense rows carry the expense `version` and full `before`/`after` states (the
    expense's revision history). Other entities (group, member, category, payment,
    split rule) store what changed in `after`.
    """

    __tablename__ = "history"
    __table_args__ = (
        Index("ix_history_entity", "entity", "entity_id", "created_at"),
        Index(
            "uq_history_expense_version",
            "entity_id",
            "version",
            unique=True,
            postgresql_where=text("entity = 'expense'"),
        ),
    )

    id: Mapped[UUID] = uuid_pk()
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[UUID] = mapped_column()
    version: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(40))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(String(280))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()
