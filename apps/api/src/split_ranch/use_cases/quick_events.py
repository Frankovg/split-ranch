"""Quick splits persistence. The client computes; the server recomputes and verifies."""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from split_ranch.core import clock
from split_ranch.core.actor import Actor
from split_ranch.core.errors import NotFound, Unprocessable
from split_ranch.domain import (
    LedgerExpense,
    NetEntry,
    Share,
    SplitParticipant,
    compute_balances,
    resolve_shares,
    settle,
)
from split_ranch.models import QuickEvent, QuickExpense, QuickExpenseShare, QuickParticipant
from split_ranch.schemas.quick import (
    QuickBalanceRead,
    QuickEventIn,
    QuickEventRead,
    QuickEventSummary,
    QuickExpenseRead,
    QuickParticipantRead,
    QuickShareLinkRead,
    QuickShareRead,
    QuickTransferRead,
    SharedQuickEventRead,
)
from split_ranch.use_cases.common import check_version

log = structlog.get_logger(__name__)


def _mismatch(detail: str) -> Unprocessable:
    return Unprocessable(detail, code="split_mismatch")


def _verify(data: QuickEventIn) -> None:
    """Recompute every expense and the transfers; reject differences with the client."""
    order = {p.id: (p.sort_key, str(p.id)) for p in data.participants}
    for expense in data.expenses:
        if expense.payer_participant_id is not None and expense.payer_participant_id not in order:
            raise Unprocessable("Unknown payer participant", code="invalid_split")
        shares = sorted(expense.shares, key=lambda s: order.get(s.participant_id, (10**9, "")))
        for s in shares:
            if s.participant_id not in order:
                raise Unprocessable("Unknown participant in shares", code="invalid_split")
        participants = [
            SplitParticipant(str(s.participant_id), weight=s.weight, exact_cents=s.exact_cents)
            for s in shares
        ]
        payer = str(expense.payer_participant_id or shares[0].participant_id)
        server = resolve_shares(expense.amount_cents, payer, expense.split_type, participants)
        client = [(str(s.participant_id), s.amount_cents) for s in shares]
        if [(x.id, x.amount_cents) for x in server] != client:
            log.warning("quick_split_parity_mismatch", expense_id=str(expense.id))
            raise _mismatch(f"Shares of expense {expense.id} differ from the server calculation")
    if data.transfers is not None:
        _, transfers = _result(
            [p.id for p in sorted(data.participants, key=lambda p: (p.sort_key, str(p.id)))],
            [
                (
                    e.payer_participant_id,
                    e.amount_cents,
                    [(s.participant_id, s.amount_cents) for s in e.shares],
                )
                for e in data.expenses
            ],
        )
        client_t = [
            (t.from_participant_id, t.to_participant_id, t.amount_cents) for t in data.transfers
        ]
        server_t = [(t.from_participant_id, t.to_participant_id, t.amount_cents) for t in transfers]
        if client_t != server_t:
            log.warning("quick_split_transfer_mismatch")
            raise _mismatch("Transfers differ from the server calculation")


def _result(
    participant_order: Sequence[UUID],
    expenses: Sequence[tuple[UUID | None, int, Sequence[tuple[UUID, int]]]],
) -> tuple[list[QuickBalanceRead], list[QuickTransferRead]]:
    """Balances over expenses that have a payer; transfers via the greedy settle."""
    ledger = [
        LedgerExpense(str(payer), amount, [Share(str(pid), a) for pid, a in shares])
        for payer, amount, shares in expenses
        if payer is not None
    ]
    balances = compute_balances([str(p) for p in participant_order], ledger)
    transfers = settle([NetEntry(b.id, b.net_cents) for b in balances]) if ledger else []
    return (
        [
            QuickBalanceRead(
                participant_id=UUID(b.id),
                paid_cents=b.paid_cents,
                owed_cents=b.owed_cents,
                net_cents=b.net_cents,
            )
            for b in balances
        ],
        [
            QuickTransferRead(
                from_participant_id=UUID(t.from_id),
                to_participant_id=UUID(t.to_id),
                amount_cents=t.amount_cents,
            )
            for t in transfers
        ],
    )


def _load(
    session: Session, event_id: UUID
) -> tuple[list[QuickParticipant], list[QuickExpense], dict[UUID, list[QuickExpenseShare]]]:
    participants = list(
        session.scalars(
            select(QuickParticipant)
            .where(QuickParticipant.event_id == event_id)
            .order_by(QuickParticipant.sort_key, QuickParticipant.id)
        )
    )
    expenses = list(
        session.scalars(
            select(QuickExpense)
            .where(QuickExpense.event_id == event_id)
            .order_by(QuickExpense.sort_key, QuickExpense.id)
        )
    )
    index = {p.id: i for i, p in enumerate(participants)}
    shares: dict[UUID, list[QuickExpenseShare]] = {}
    for s in session.scalars(
        select(QuickExpenseShare).where(QuickExpenseShare.event_id == event_id)
    ):
        shares.setdefault(s.quick_expense_id, []).append(s)
    for lst in shares.values():
        lst.sort(key=lambda s: index.get(s.participant_id, 0))
    return participants, expenses, shares


def _read(session: Session, event: QuickEvent) -> QuickEventRead:
    participants, expenses, shares = _load(session, event.id)
    balances, transfers = _result(
        [p.id for p in participants],
        [
            (
                e.payer_participant_id,
                e.amount_cents,
                [(s.participant_id, s.amount_cents) for s in shares.get(e.id, [])],
            )
            for e in expenses
        ],
    )
    return QuickEventRead(
        id=event.id,
        title=event.title,
        mode=event.mode,
        currency=event.currency,
        version=event.version,
        participants=[QuickParticipantRead.model_validate(p) for p in participants],
        expenses=[
            QuickExpenseRead(
                id=e.id,
                payer_participant_id=e.payer_participant_id,
                amount_cents=e.amount_cents,
                description=e.description,
                split_type=e.split_type,
                shares=[QuickShareRead.model_validate(s) for s in shares.get(e.id, [])],
            )
            for e in expenses
        ],
        balances=balances,
        transfers=transfers,
        share_token=event.share_token,
        share_expires_at=event.share_expires_at,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def _own_event(
    session: Session, actor: Actor, event_id: UUID, *, for_update: bool = False
) -> QuickEvent:
    stmt = select(QuickEvent).where(
        QuickEvent.id == event_id,
        QuickEvent.owner_user_id == actor.user_id,
        QuickEvent.deleted_at.is_(None),
    )
    if for_update:
        stmt = stmt.with_for_update()
    event = session.scalars(stmt).first()
    if event is None:
        raise NotFound("Quick event not found")
    return event


def save_quick_event(
    session: Session, actor: Actor, event_id: UUID, data: QuickEventIn, if_match: int | None
) -> tuple[QuickEventRead, bool]:
    """Upsert the whole event. Returns (event, created)."""
    _verify(data)
    existing = session.scalars(
        select(QuickEvent).where(QuickEvent.id == event_id).with_for_update()
    ).first()
    created = existing is None
    if existing is not None:
        if existing.owner_user_id != actor.user_id or existing.deleted_at is not None:
            raise NotFound("Quick event not found")
        check_version(if_match, existing.version, current_body=_read(session, existing))
        event = existing
        event.title = data.title.strip()
        event.mode = data.mode
        event.version += 1
        event.updated_at = clock.now()
        session.execute(delete(QuickExpense).where(QuickExpense.event_id == event.id))
        session.execute(delete(QuickParticipant).where(QuickParticipant.event_id == event.id))
        session.flush()
    else:
        event = QuickEvent(
            id=event_id,
            owner_user_id=actor.user_id,
            title=data.title.strip(),
            mode=data.mode,
            currency=data.currency,
            version=1,
        )
        session.add(event)
        session.flush()

    for p in data.participants:
        session.add(
            QuickParticipant(
                id=p.id,
                event_id=event.id,
                name=p.name.strip(),
                sort_key=p.sort_key,
                weight=p.weight,
            )
        )
    session.flush()
    for i, e in enumerate(data.expenses):
        session.add(
            QuickExpense(
                id=e.id,
                event_id=event.id,
                payer_participant_id=e.payer_participant_id,
                amount_cents=e.amount_cents,
                description=e.description,
                split_type=e.split_type,
                sort_key=i,
            )
        )
    session.flush()
    for e in data.expenses:
        for s in e.shares:
            session.add(
                QuickExpenseShare(
                    quick_expense_id=e.id,
                    participant_id=s.participant_id,
                    event_id=event.id,
                    weight=s.weight,
                    exact_cents=s.exact_cents,
                    amount_cents=s.amount_cents,
                )
            )
    session.flush()
    session.commit()
    return _read(session, event), created


def get_quick_event(session: Session, actor: Actor, event_id: UUID) -> QuickEventRead:
    return _read(session, _own_event(session, actor, event_id))


def list_quick_events(
    session: Session, actor: Actor, *, limit: int, cursor: str | None
) -> tuple[list[QuickEventSummary], str | None]:
    stmt = select(QuickEvent).where(
        QuickEvent.owner_user_id == actor.user_id, QuickEvent.deleted_at.is_(None)
    )
    if cursor:
        try:
            ts_raw, id_raw = cursor.split("_", 1)
            ts, last_id = datetime.fromisoformat(ts_raw), UUID(id_raw)
        except ValueError as exc:
            raise Unprocessable("Invalid cursor") from exc
        stmt = stmt.where(
            (QuickEvent.updated_at < ts)
            | ((QuickEvent.updated_at == ts) & (QuickEvent.id < last_id))
        )
    rows = list(
        session.scalars(
            stmt.order_by(QuickEvent.updated_at.desc(), QuickEvent.id.desc()).limit(limit + 1)
        )
    )
    items = []
    for ev in rows[:limit]:
        participants, expenses, _ = _load(session, ev.id)
        items.append(
            QuickEventSummary(
                id=ev.id,
                title=ev.title,
                mode=ev.mode,
                total_cents=sum(e.amount_cents for e in expenses),
                participant_count=len(participants),
                version=ev.version,
                updated_at=ev.updated_at,
            )
        )
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = f"{last.updated_at.isoformat()}_{last.id}"
    return items, next_cursor


def delete_quick_event(
    session: Session, actor: Actor, event_id: UUID, if_match: int | None
) -> None:
    event = _own_event(session, actor, event_id, for_update=True)
    check_version(if_match, event.version, required=False)
    event.deleted_at = clock.now()
    event.share_token = None
    session.commit()


def share_quick_event(
    session: Session, actor: Actor, event_id: UUID, *, base_url: str, days: int
) -> QuickShareLinkRead:
    event = _own_event(session, actor, event_id, for_update=True)
    now = clock.now()
    if event.share_token is None or event.share_expires_at is None or event.share_expires_at <= now:
        event.share_token = secrets.token_urlsafe(16)  # 22 chars
        event.share_expires_at = now + timedelta(days=days)
        session.commit()
    assert event.share_token is not None and event.share_expires_at is not None
    return QuickShareLinkRead(
        share_token=event.share_token,
        url=f"{base_url.rstrip('/')}/q/{event.share_token}",
        expires_at=event.share_expires_at,
    )


def get_shared_quick_event(session: Session, token: str) -> SharedQuickEventRead:
    event = session.scalars(
        select(QuickEvent).where(QuickEvent.share_token == token, QuickEvent.deleted_at.is_(None))
    ).first()
    if event is None or event.share_expires_at is None or event.share_expires_at <= clock.now():
        raise NotFound("Shared event not found")
    full = _read(session, event)
    names = {p.id: p.name for p in full.participants}
    return SharedQuickEventRead(
        title=full.title,
        currency=full.currency,
        participants=[p.name for p in full.participants],
        expenses=[
            {
                "description": e.description,
                "amount_cents": e.amount_cents,
                "payer": names.get(e.payer_participant_id) if e.payer_participant_id else None,
                "shares": [
                    {"name": names.get(s.participant_id), "amount_cents": s.amount_cents}
                    for s in e.shares
                ],
            }
            for e in full.expenses
        ],
        balances=[
            {"name": names.get(b.participant_id), "net_cents": b.net_cents} for b in full.balances
        ],
        transfers=[
            {
                "from": names.get(t.from_participant_id),
                "to": names.get(t.to_participant_id),
                "amount_cents": t.amount_cents,
            }
            for t in full.transfers
        ],
    )
