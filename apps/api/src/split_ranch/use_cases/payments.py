"""Payments between members: record, confirm, dispute, cancel, list.

    sent -> confirmed | disputed | cancelled      disputed -> confirmed | cancelled

The debtor (`from`) records a payment as `sent`; the creditor (`to`) confirms or disputes
it. A creditor recording a payment directly creates it `confirmed` (cash received). Only
confirmed payments count in the balance. A confirmed payment is never changed: a mistake
is fixed with a payment in the opposite direction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from split_ranch.core import clock
from split_ranch.core.actor import GroupActor
from split_ranch.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from split_ranch.models import Payment
from split_ranch.repositories import groups as grepo
from split_ranch.repositories import payments as prepo
from split_ranch.schemas.payments import PaymentCreate, PaymentDispute, PaymentNote, PaymentRead
from split_ranch.use_cases.common import (
    audit,
    check_version,
    lock_group_for_balance_write,
    require_active,
)
from split_ranch.use_cases.notifications import (
    EventKind,
    NotificationEvent,
    Notifier,
    NullNotifier,
)
from split_ranch.use_cases.pagination import DEFAULT_PAGE, clamp_limit, decode_cursor, encode_cursor

# Allowed transitions: action -> (who, from statuses, to status)
_TRANSITIONS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "confirm": ("to", ("sent", "disputed"), "confirmed"),
    "dispute": ("to", ("sent",), "disputed"),
    "cancel": ("from", ("sent", "disputed"), "cancelled"),
}


_NO_NOTIFIER = NullNotifier()

# Transition -> (event kind, who is told: the other party of the payment).
_TRANSITION_EVENTS: dict[str, tuple[EventKind, str]] = {
    "confirm": ("payment_confirmed", "from"),
    "dispute": ("payment_disputed", "from"),
    "cancel": ("payment_cancelled", "to"),
}


def _event(kind: EventKind, actor: GroupActor, payment: Payment, side: str) -> NotificationEvent:
    member = payment.from_member_id if side == "from" else payment.to_member_id
    return NotificationEvent(kind, actor.group_id, actor.user_id, payment.id, frozenset({member}))


def _snapshot(p: Payment) -> dict[str, object]:
    return {
        "from_member_id": str(p.from_member_id),
        "to_member_id": str(p.to_member_id),
        "amount_cents": p.amount_cents,
        "status": p.status,
        "method": p.method,
        "note": p.note,
        "version": p.version,
    }


def _same_payload(p: Payment, data: PaymentCreate, actor: GroupActor) -> bool:
    return (
        p.created_by_user_id == actor.user_id
        and p.from_member_id == data.from_member_id
        and p.to_member_id == data.to_member_id
        and p.amount_cents == data.amount_cents
        and p.method == data.method
        and p.note == data.note
    )


def _replay_create(
    session: Session, actor: GroupActor, data: PaymentCreate
) -> tuple[int, PaymentRead] | None:
    """The stored payment for a retry of the same id (200), or None if there is none yet."""
    existing = prepo.get_payment(session, actor.group_id, data.id)
    if existing is None:
        return None
    if not _same_payload(existing, data, actor):
        raise Conflict("A payment with this id already exists", code="id_conflict")
    return 200, PaymentRead.model_validate(existing)


def record_payment(
    session: Session,
    actor: GroupActor,
    data: PaymentCreate,
    *,
    notifier: Notifier = _NO_NOTIFIER,
) -> tuple[int, PaymentRead]:
    """Returns (201, created) or (200, stored) for an identical retry of the same id."""
    require_active(actor)
    lock_group_for_balance_write(session, actor.group_id)
    if (replay := _replay_create(session, actor, data)) is not None:
        return replay
    if data.from_member_id == data.to_member_id:
        raise Unprocessable("A payment needs two different members", code="invalid_payment")
    if actor.member_id == data.from_member_id:
        status = "sent"
    elif actor.member_id == data.to_member_id:
        status = "confirmed"
    else:
        raise Forbidden("Only the payer or the receiver can record a payment")
    for member_id in (data.from_member_id, data.to_member_id):
        member = grepo.get_member(session, actor.group_id, member_id)
        if member is None or member.status != "active":
            raise Unprocessable("Both members must be active in this group", code="invalid_payment")
    now = clock.now()
    payment = Payment(
        id=data.id,
        group_id=actor.group_id,
        from_member_id=data.from_member_id,
        to_member_id=data.to_member_id,
        amount_cents=data.amount_cents,
        status=status,
        method=data.method,
        note=data.note,
        created_by_user_id=actor.user_id,
        confirmed_at=now if status == "confirmed" else None,
        confirmed_by_user_id=actor.user_id if status == "confirmed" else None,
        version=1,
    )
    try:
        with session.begin_nested():
            session.add(payment)
            session.flush()
    except IntegrityError as exc:
        # A concurrent retry with the same id committed first: answer as a retry does.
        if (replay := _replay_create(session, actor, data)) is not None:
            return replay
        # The id exists in another group: same answer, without saying where.
        raise Conflict("A payment with this id already exists", code="id_conflict") from exc
    audit(
        session,
        group_id=actor.group_id,
        entity="payment",
        entity_id=payment.id,
        actor_user_id=actor.user_id,
        action="create",
        diff=_snapshot(payment),
    )
    session.commit()
    # Sent: the receiver should confirm it. Recorded as received (cash): tell the payer.
    if status == "sent":
        notifier.notify(_event("payment_sent", actor, payment, "to"))
    else:
        notifier.notify(_event("payment_recorded", actor, payment, "from"))
    return 201, PaymentRead.model_validate(payment)


def transition_payment(
    session: Session,
    actor: GroupActor,
    payment_id: UUID,
    action: str,
    data: PaymentNote | PaymentDispute,
    if_match: int | None,
    *,
    notifier: Notifier = _NO_NOTIFIER,
) -> PaymentRead:
    require_active(actor)
    who, allowed_from, target = _TRANSITIONS[action]
    payment = prepo.get_payment(session, actor.group_id, payment_id, for_update=True)
    if payment is None:
        raise NotFound("Payment not found")
    party = payment.to_member_id if who == "to" else payment.from_member_id
    if actor.member_id != party:
        side = "receiver" if who == "to" else "payer"
        raise Forbidden(f"Only the payment's {side} can do this")
    check_version(if_match, payment.version, current_body=PaymentRead.model_validate(payment))
    if payment.status not in allowed_from:
        raise Conflict(
            f"Cannot {action} a payment that is {payment.status}",
            code="payment_state_changed",
            extra={"current": PaymentRead.model_validate(payment)},
        )
    before = _snapshot(payment)
    payment.status = target
    if data.note is not None:
        payment.note = data.note
    if target == "confirmed":
        payment.confirmed_at = clock.now()
        payment.confirmed_by_user_id = actor.user_id
    payment.version += 1
    audit(
        session,
        group_id=actor.group_id,
        entity="payment",
        entity_id=payment.id,
        actor_user_id=actor.user_id,
        action=action,
        diff={"before": before, "after": _snapshot(payment)},
    )
    session.commit()
    kind, side = _TRANSITION_EVENTS[action]
    notifier.notify(_event(kind, actor, payment, side))
    return PaymentRead.model_validate(payment)


def get_payment(session: Session, actor: GroupActor, payment_id: UUID) -> PaymentRead:
    payment = prepo.get_payment(session, actor.group_id, payment_id)
    if payment is None:
        raise NotFound("Payment not found")
    return PaymentRead.model_validate(payment)


def _parse_cursor(data: dict[str, Any]) -> tuple[datetime, UUID]:
    return datetime.fromisoformat(data["t"]), UUID(data["i"])


def list_payments(
    session: Session,
    actor: GroupActor,
    *,
    limit: int = DEFAULT_PAGE,
    cursor: str | None = None,
    status: list[str] | None = None,
) -> tuple[list[PaymentRead], str | None]:
    limit = clamp_limit(limit)
    rows = prepo.list_payments(
        session,
        actor.group_id,
        limit=limit + 1,
        after=decode_cursor(cursor, _parse_cursor) if cursor else None,
        statuses=status,
    )
    items = [PaymentRead.model_validate(p) for p in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor({"t": last.created_at.isoformat(), "i": str(last.id)})
    return items, next_cursor
