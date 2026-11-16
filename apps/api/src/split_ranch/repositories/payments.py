"""Group-scoped payment queries."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from split_ranch.models import Payment


def get_payment(
    session: Session, group_id: UUID, payment_id: UUID, *, for_update: bool = False
) -> Payment | None:
    stmt = select(Payment).where(Payment.group_id == group_id, Payment.id == payment_id)
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


def list_payments(
    session: Session,
    group_id: UUID,
    *,
    limit: int,
    after: tuple[datetime, UUID] | None = None,
    statuses: Sequence[str] | None = None,
) -> Sequence[Payment]:
    """Newest first; keyset pagination on (created_at DESC, id DESC)."""
    stmt = select(Payment).where(Payment.group_id == group_id)
    if statuses:
        stmt = stmt.where(Payment.status.in_(statuses))
    if after is not None:
        ts, i = after
        stmt = stmt.where(
            or_(Payment.created_at < ts, and_(Payment.created_at == ts, Payment.id < i))
        )
    stmt = stmt.order_by(Payment.created_at.desc(), Payment.id.desc()).limit(limit)
    return session.scalars(stmt).all()


def payments_with_status(
    session: Session, group_id: UUID, statuses: Sequence[str]
) -> Sequence[Payment]:
    return session.scalars(
        select(Payment)
        .where(Payment.group_id == group_id, Payment.status.in_(statuses))
        .order_by(Payment.created_at, Payment.id)
    ).all()
