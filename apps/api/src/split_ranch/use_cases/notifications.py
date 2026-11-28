"""Push notifications: device registration and delivery of group events.

Use cases emit a `NotificationEvent` through a `Notifier` after their commit. In the API
the notifier queues `dispatch_safely` as a FastAPI background task, so the push is sent
after the response and a failure never affects the request. Nothing is ever sent to the
member who did the action, to members who left, or to users whose switches are off.

There is no worker, so push receipts are read lazily: each token keeps its latest unchecked
ticket, and the next time a notification goes to that device a ticket older than 15 min (and
younger than 24 h, Expo's retention) is checked first. Tokens Expo reports as
`DeviceNotRegistered`, in a ticket or a receipt, are deleted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal, Protocol
from uuid import UUID

import sentry_sdk
import structlog
from sqlalchemy.orm import Session

from split_ranch.core import clock
from split_ranch.core.actor import Actor
from split_ranch.integrations.expo_push import (
    DEVICE_NOT_REGISTERED,
    ExpoPushClient,
    ExpoPushError,
    PushMessage,
)
from split_ranch.models import PushToken, User
from split_ranch.repositories import expenses as erepo
from split_ranch.repositories import groups as grepo
from split_ranch.repositories import notifications as nrepo
from split_ranch.repositories import payments as prepo
from split_ranch.schemas.notifications import PushTokenDelete, PushTokenIn
from split_ranch.use_cases.notification_texts import normalize_locale, render_body

log = structlog.get_logger(__name__)

EventKind = Literal[
    "expense_created",
    "expense_updated",
    "expense_deleted",
    "payment_sent",
    "payment_recorded",
    "payment_confirmed",
    "payment_disputed",
    "payment_cancelled",
    "member_joined",
]

# Which in-app switch (users.notification_prefs) controls each event kind.
PREF_FOR_KIND: dict[str, str] = {
    "expense_created": "expense_created",
    "expense_updated": "expense_changed",
    "expense_deleted": "expense_changed",
    "payment_sent": "payments",
    "payment_recorded": "payments",
    "payment_confirmed": "payments",
    "payment_disputed": "payments",
    "payment_cancelled": "payments",
    "member_joined": "member_joined",
}

# Android notification channels, created by the app (src/features/notifications/channels.ts).
CHANNEL_FOR_KIND: dict[str, str] = {
    "expense_created": "expenses",
    "expense_updated": "expenses",
    "expense_deleted": "expenses",
    "payment_sent": "payments",
    "payment_recorded": "payments",
    "payment_confirmed": "payments",
    "payment_disputed": "payments",
    "payment_cancelled": "payments",
    "member_joined": "group",
}

RECEIPT_DELAY = timedelta(minutes=15)
RECEIPT_RETENTION = timedelta(hours=24)


@dataclass(frozen=True)
class NotificationEvent:
    kind: EventKind
    group_id: UUID
    actor_user_id: UUID
    # The expense, the payment or the member that joined.
    entity_id: UUID
    # Members to notify; None means every active member. The actor is always left out.
    recipient_member_ids: frozenset[UUID] | None = None


class Notifier(Protocol):
    def notify(self, event: NotificationEvent) -> None: ...


class NullNotifier:
    """Sends nothing (push disabled, scripts, unit tests)."""

    def notify(self, event: NotificationEvent) -> None:
        return None


# ------------------------------------------------------------ registration


def register_token(session: Session, actor: Actor, data: PushTokenIn) -> None:
    nrepo.upsert_token(session, actor.user_id, data.token, data.platform, data.locale)
    session.commit()


def unregister_token(session: Session, actor: Actor, data: PushTokenDelete) -> None:
    """Idempotent: deleting a token that is gone (or belongs to someone else) is a no-op."""
    nrepo.delete_token(session, actor.user_id, data.token)
    session.commit()


# --------------------------------------------------------------- delivery


@dataclass(frozen=True)
class _Content:
    group_name: str
    actor_name: str | None
    description: str
    amount_cents: int


def _url(event: NotificationEvent) -> str:
    group = f"/group/{event.group_id}"
    # A new expense opens the group, so the list shows it among the others; an edit opens
    # the expense itself to show what changed.
    if event.kind == "expense_updated":
        return f"{group}/expense/{event.entity_id}"
    if event.kind.startswith("payment_"):
        return f"{group}/settle"
    return group


def _content(session: Session, event: NotificationEvent) -> _Content | None:
    group = grepo.get_group(session, event.group_id)
    if group is None:
        return None
    actor = session.get(User, event.actor_user_id)
    actor_name = actor.display_name if actor is not None else None
    description, amount = "", 0
    if event.kind.startswith("expense_"):
        expense = erepo.get_expense(session, event.group_id, event.entity_id)
        if expense is None:
            return None
        description, amount = expense.description, expense.amount_cents
    elif event.kind.startswith("payment_"):
        payment = prepo.get_payment(session, event.group_id, event.entity_id)
        if payment is None:
            return None
        amount = payment.amount_cents
    return _Content(group.name, actor_name, description, amount)


def _pref(user: User, key: str) -> bool:
    prefs = user.notification_prefs or {}
    return bool(prefs.get(key, True))


def _recipient_users(session: Session, event: NotificationEvent) -> set[UUID]:
    members = nrepo.active_member_users(session, event.group_id)
    if event.recipient_member_ids is not None:
        members = {m: u for m, u in members.items() if m in event.recipient_member_ids}
    candidates = {u for u in members.values() if u != event.actor_user_id}
    pref = PREF_FOR_KIND[event.kind]
    users = nrepo.users_by_id(session, candidates)
    return {uid for uid, user in users.items() if _pref(user, "enabled") and _pref(user, pref)}


def _check_receipts(
    session: Session, client: ExpoPushClient, tokens: list[PushToken]
) -> list[PushToken]:
    """Read due receipts; returns the tokens still worth sending to."""
    now = clock.now()
    due: dict[str, PushToken] = {}
    for token in tokens:
        if token.last_ticket_id is None or token.last_ticket_at is None:
            continue
        age = now - token.last_ticket_at
        if age >= RECEIPT_RETENTION:
            # Expo no longer has the receipt: forget the ticket.
            nrepo.set_ticket(session, token.id, None, None)
            token.last_ticket_id = None
        elif age >= RECEIPT_DELAY:
            due[token.last_ticket_id] = token
    if not due:
        return tokens
    try:
        receipts = client.get_receipts(list(due))
    except ExpoPushError as exc:
        log.warning("push_receipts_failed", error=str(exc))
        return tokens
    dead: set[UUID] = set()
    for ticket_id, receipt in receipts.items():
        token = due[ticket_id]
        if receipt.status == "error":
            log.warning("push_receipt_error", error=receipt.error)
            if receipt.error == DEVICE_NOT_REGISTERED:
                dead.add(token.id)
                continue
        nrepo.set_ticket(session, token.id, None, None)
        token.last_ticket_id = None
    nrepo.delete_tokens(session, dead)
    return [t for t in tokens if t.id not in dead]


def dispatch(session: Session, client: ExpoPushClient, event: NotificationEvent) -> int:
    """Send the event's notifications; returns how many messages were sent."""
    user_ids = _recipient_users(session, event)
    tokens = list(nrepo.tokens_for_users(session, user_ids))
    if not tokens:
        return 0
    tokens = _check_receipts(session, client, tokens)
    content = _content(session, event)
    if not tokens or content is None:
        session.commit()
        return 0

    data = {"type": event.kind, "group_id": str(event.group_id), "url": _url(event)}
    messages = [
        PushMessage(
            to=token.token,
            title=content.group_name,
            body=render_body(
                event.kind,
                normalize_locale(token.locale),
                actor=content.actor_name,
                description=content.description,
                amount_cents=content.amount_cents,
            ),
            channel_id=CHANNEL_FOR_KIND[event.kind],
            data=data,
        )
        for token in tokens
    ]
    try:
        tickets = client.send(messages)
    except ExpoPushError:
        session.commit()  # keep the receipt bookkeeping done above
        raise
    now = clock.now()
    dead: set[UUID] = set()
    for token, ticket in zip(tokens, tickets, strict=True):
        if ticket.status == "ok":
            # Keep the oldest unchecked ticket: its receipt is checked first.
            if token.last_ticket_id is None and ticket.id:
                nrepo.set_ticket(session, token.id, ticket.id, now)
        elif ticket.error == DEVICE_NOT_REGISTERED:
            dead.add(token.id)
        else:
            log.warning("push_ticket_error", error=ticket.error, kind=event.kind)
    nrepo.delete_tokens(session, dead)
    session.commit()
    log.info("push_sent", kind=event.kind, messages=len(messages), unregistered=len(dead))
    return len(messages)


def dispatch_safely(
    session_factory: Callable[[], Session], client: ExpoPushClient, event: NotificationEvent
) -> None:
    """Background entry point: its own session, and errors are only reported."""
    try:
        with session_factory() as session:
            dispatch(session, client, event)
    except Exception as exc:
        log.exception("push_dispatch_failed", kind=event.kind)
        sentry_sdk.capture_exception(exc)
