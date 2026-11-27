"""Expenses: create, preview, read, list, summary, update, delete, revisions.

Any active member can change any expense at any time; every change is a `history` row.
Splits are resolved against the group's active members when they are created, or when an
edit changes `split` or `participants`. Any other edit keeps the stored participants and
inputs (an amount change re-allocates over them), and a rule change never re-splits
existing expenses.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from split_ranch.core import clock
from split_ranch.core.actor import GroupActor
from split_ranch.core.errors import Conflict, NotFound, Unprocessable
from split_ranch.models import Expense, ExpenseShare, History
from split_ranch.repositories import expenses as erepo
from split_ranch.repositories import groups as grepo
from split_ranch.repositories.expenses import ExpenseFilters
from split_ranch.schemas.expenses import (
    CategoryTotalRead,
    ExpenseCreate,
    ExpenseDeleteIn,
    ExpensePreviewIn,
    ExpenseRead,
    ExpenseUpdate,
    PayerTotalRead,
    RevisionRead,
    SplitPreviewRead,
    SummaryRead,
)
from split_ranch.schemas.split import EqualSplit, ShareRead, SplitSpec, spec_from_json
from split_ranch.use_cases.common import (
    check_version,
    lock_group_for_balance_write,
    require_active,
)
from split_ranch.use_cases.notifications import NotificationEvent, Notifier, NullNotifier
from split_ranch.use_cases.split_resolution import (
    Resolution,
    ResolvedShare,
    RuleData,
    resolve_expense_split,
    rule_from_spec,
    spec_from_stored,
)

_NO_NOTIFIER = NullNotifier()

DEFAULT_PAGE = 50
MAX_PAGE = 200


# ---------------------------------------------------------------- helpers


def _category_rule(session: Session, group_id: UUID, category_id: UUID | None) -> RuleData | None:
    if category_id is None:
        return None
    category = grepo.get_category(session, group_id, category_id)
    if category is None or category.split_rule is None:
        return None
    return rule_from_spec(spec_from_json(category.split_rule))


def _default_rule(session: Session, group_id: UUID) -> RuleData | None:
    group = grepo.get_group(session, group_id)
    if group is None:
        return None
    return rule_from_spec(spec_from_json(group.split_rule))


def _resolve(
    session: Session,
    group_id: UUID,
    *,
    amount_cents: int,
    payer_member_id: UUID,
    category_id: UUID | None,
    split: SplitSpec | None,
    participants: Sequence[UUID] | None,
) -> Resolution:
    members = grepo.list_members(session, group_id)
    active = [m.id for m in grepo.active_members(session, group_id)]
    return resolve_expense_split(
        amount_cents=amount_cents,
        payer_member_id=payer_member_id,
        override=split,
        participants=participants,
        category_rule=_category_rule(session, group_id, category_id),
        default_rule=_default_rule(session, group_id),
        members=active,
        canonical_order=[m.id for m in members],
    )


def _check_payer(session: Session, group_id: UUID, payer_id: UUID) -> None:
    member = grepo.get_member(session, group_id, payer_id)
    if member is None or member.status != "active":
        raise Unprocessable("Payer is not an active member of this group", code="invalid_payer")


def _check_category(session: Session, group_id: UUID, category_id: UUID | None) -> None:
    if category_id is None:
        return
    if grepo.get_category(session, group_id, category_id, include_archived=False) is None:
        raise Unprocessable("Unknown or archived category", code="invalid_category")


def _write_shares(session: Session, expense: Expense, resolution: Resolution) -> None:
    session.execute(
        delete(ExpenseShare).where(
            ExpenseShare.group_id == expense.group_id,
            ExpenseShare.expense_id == expense.id,
        )
    )
    for i, s in enumerate(resolution.shares):
        session.add(
            ExpenseShare(
                expense_id=expense.id,
                group_id=expense.group_id,
                member_id=s.member_id,
                sort_key=i,
                amount_cents=s.amount_cents,
                weight=s.weight,
                basis_points=s.basis_points,
                exact_cents=s.exact_cents,
            )
        )
    expense.split_type = resolution.split_type
    expense.split_origin = resolution.split_origin
    expense.participant_mode = resolution.participant_mode
    expense.rule_fallback = resolution.rule_fallback
    session.flush()


def _stored_shares(session: Session, expense: Expense) -> list[ResolvedShare]:
    rows = erepo.shares_for(session, expense.group_id, [expense.id]).get(expense.id, [])
    return [
        ResolvedShare(s.member_id, s.amount_cents, s.weight, s.basis_points, s.exact_cents)
        for s in rows
    ]


def snapshot_json(session: Session, expense: Expense) -> dict[str, Any]:
    """Expense state stored in revisions (shares included)."""
    return {
        "id": str(expense.id),
        "amount_cents": expense.amount_cents,
        "description": expense.description,
        "notes": expense.notes,
        "category_id": str(expense.category_id) if expense.category_id else None,
        "payer_member_id": str(expense.payer_member_id),
        "expense_date": expense.expense_date.isoformat(),
        "split_type": expense.split_type,
        "split_origin": expense.split_origin,
        "participant_mode": expense.participant_mode,
        "rule_fallback": expense.rule_fallback,
        "source": expense.source,
        "deleted_at": expense.deleted_at.isoformat() if expense.deleted_at else None,
        "version": expense.version,
        "shares": [
            {
                "member_id": str(s.member_id),
                "amount_cents": s.amount_cents,
                "weight": s.weight,
                "basis_points": s.basis_points,
                "exact_cents": s.exact_cents,
            }
            for s in _stored_shares(session, expense)
        ],
    }


def _revision(
    session: Session,
    expense: Expense,
    action: str,
    actor_user_id: UUID | None,
    before: dict[str, Any] | None,
    reason: str | None = None,
) -> None:
    session.add(
        History(
            group_id=expense.group_id,
            entity="expense",
            entity_id=expense.id,
            version=expense.version,
            action=action,
            actor_user_id=actor_user_id,
            reason=reason,
            before=before,
            after=snapshot_json(session, expense),
        )
    )


def _shares_read(shares: Sequence[ResolvedShare]) -> list[ShareRead]:
    return [
        ShareRead(
            member_id=s.member_id,
            amount_cents=s.amount_cents,
            weight=s.weight,
            basis_points=s.basis_points,
            exact_cents=s.exact_cents,
        )
        for s in shares
    ]


def to_read(session: Session, actor: GroupActor, expense: Expense) -> ExpenseRead:
    return ExpenseRead(
        id=expense.id,
        group_id=expense.group_id,
        version=expense.version,
        category_id=expense.category_id,
        payer_member_id=expense.payer_member_id,
        amount_cents=expense.amount_cents,
        description=expense.description,
        notes=expense.notes,
        expense_date=expense.expense_date,
        split_type=expense.split_type,
        split_origin=expense.split_origin,
        participant_mode=expense.participant_mode,
        rule_fallback=expense.rule_fallback,
        source=expense.source,
        shares=_shares_read(_stored_shares(session, expense)),
        created_by_user_id=expense.created_by_user_id,
        updated_by_user_id=expense.updated_by_user_id,
        created_at=expense.created_at,
        updated_at=expense.updated_at,
        deleted_at=expense.deleted_at,
        can_edit=expense.deleted_at is None and actor.status == "active",
    )


def _load(
    session: Session, actor: GroupActor, expense_id: UUID, *, for_update: bool = False
) -> Expense:
    expense = erepo.get_expense(session, actor.group_id, expense_id, for_update=for_update)
    if expense is None:
        raise NotFound("Expense not found")
    return expense


def _require_no_left_members(session: Session, expense: Expense) -> None:
    """D2: a member who left has a zero balance that no edit may change."""
    involved = {expense.payer_member_id} | {s.member_id for s in _stored_shares(session, expense)}
    for member_id in involved:
        member = grepo.get_member(session, expense.group_id, member_id)
        if member is None or member.status != "active":
            raise Conflict("This expense involves a member who left the group", code="member_left")


# ----------------------------------------------------------------- create


def preview_split(session: Session, actor: GroupActor, data: ExpensePreviewIn) -> SplitPreviewRead:
    _check_payer(session, actor.group_id, data.payer_member_id)
    _check_category(session, actor.group_id, data.category_id)
    res = _resolve(
        session,
        actor.group_id,
        amount_cents=data.amount_cents,
        payer_member_id=data.payer_member_id,
        category_id=data.category_id,
        split=data.split,
        participants=data.participants,
    )
    return SplitPreviewRead(
        split_type=res.split_type,
        split_origin=res.split_origin,
        participant_mode=res.participant_mode,
        rule_fallback=res.rule_fallback,
        shares=_shares_read(res.shares),
    )


@dataclass(frozen=True)
class CreateResult:
    status: int
    body: dict[str, Any]
    version: int


def _same_create(
    session: Session, actor: GroupActor, existing: Expense, data: ExpenseCreate
) -> bool:
    """A retry must carry the same normalised payload, split included."""
    if not (
        existing.created_by_user_id == actor.user_id
        and existing.deleted_at is None
        and existing.amount_cents == data.amount_cents
        and existing.description == data.description
        and existing.notes == data.notes
        and existing.category_id == data.category_id
        and existing.payer_member_id == data.payer_member_id
        and existing.expense_date == data.expense_date
        and existing.source == data.source
    ):
        return False
    stored = [(s.member_id, s.amount_cents) for s in _stored_shares(session, existing)]
    try:
        res = _resolve(
            session,
            actor.group_id,
            amount_cents=data.amount_cents,
            payer_member_id=data.payer_member_id,
            category_id=data.category_id,
            split=data.split,
            participants=data.participants,
        )
    except Exception:
        return False
    return res.split_type == existing.split_type and stored == [
        (s.member_id, s.amount_cents) for s in res.shares
    ]


def create_expense(
    session: Session,
    actor: GroupActor,
    data: ExpenseCreate,
    *,
    trusted_source: bool = False,
    notifier: Notifier = _NO_NOTIFIER,
) -> CreateResult:
    """Create an expense. Public clients may only use `source='manual'`.

    Idempotent through the client-generated `id`: retrying the same expense returns the
    stored one (200); the same id with a different payload is `409 id_conflict`.
    """
    require_active(actor)
    if data.source != "manual" and not trusted_source:
        raise Unprocessable("Only manual expenses can be created by clients", code="invalid_source")
    lock_group_for_balance_write(session, actor.group_id)

    if data.id is not None:
        existing = erepo.get_expense(session, actor.group_id, data.id)
        if existing is not None:
            if not _same_create(session, actor, existing, data):
                raise Conflict("An expense with this id already exists", code="id_conflict")
            body = to_read(session, actor, existing).model_dump(mode="json")
            return CreateResult(200, body, existing.version)

    _check_payer(session, actor.group_id, data.payer_member_id)
    _check_category(session, actor.group_id, data.category_id)
    resolution = _resolve(
        session,
        actor.group_id,
        amount_cents=data.amount_cents,
        payer_member_id=data.payer_member_id,
        category_id=data.category_id,
        split=data.split,
        participants=data.participants,
    )
    expense = Expense(
        group_id=actor.group_id,
        category_id=data.category_id,
        payer_member_id=data.payer_member_id,
        amount_cents=data.amount_cents,
        description=data.description,
        notes=data.notes,
        expense_date=data.expense_date,
        split_type=resolution.split_type,
        split_origin=resolution.split_origin,
        source=data.source,
        created_by_user_id=actor.user_id,
        updated_by_user_id=actor.user_id,
        version=1,
        # Set here (not by the DB default) so it orders expenses within a day by creation.
        created_at=clock.now(),
    )
    if data.id is not None:
        expense.id = data.id
    try:
        with session.begin_nested():
            session.add(expense)
            session.flush()
    except IntegrityError as exc:
        # The id is taken in another group: same answer, without saying where.
        raise Conflict("An expense with this id already exists", code="id_conflict") from exc
    _write_shares(session, expense, resolution)
    _revision(session, expense, "create", actor.user_id, None)
    session.flush()
    body = to_read(session, actor, expense).model_dump(mode="json")
    session.commit()
    # Only a real creation notifies: the idempotent retry above returned already.
    notifier.notify(NotificationEvent("expense_created", actor.group_id, actor.user_id, expense.id))
    return CreateResult(201, body, expense.version)


# ------------------------------------------------------------------ reads


def get_expense(session: Session, actor: GroupActor, expense_id: UUID) -> ExpenseRead:
    return to_read(session, actor, _load(session, actor, expense_id))


def _encode_cursor(d: date, c: datetime, i: UUID) -> str:
    raw = json.dumps({"d": d.isoformat(), "c": c.isoformat(), "i": str(i)}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[date, datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return date.fromisoformat(data["d"]), datetime.fromisoformat(data["c"]), UUID(data["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise Unprocessable("Invalid cursor") from exc


def _check_range(filters: ExpenseFilters) -> None:
    if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
        raise Unprocessable("`from` must not be after `to`")


def list_expenses(
    session: Session,
    actor: GroupActor,
    filters: ExpenseFilters,
    *,
    limit: int = DEFAULT_PAGE,
    cursor: str | None = None,
) -> tuple[list[ExpenseRead], str | None]:
    _check_range(filters)
    limit = max(1, min(limit, MAX_PAGE))
    rows = erepo.list_expenses(
        session,
        actor.group_id,
        filters,
        limit=limit + 1,
        after=_decode_cursor(cursor) if cursor else None,
    )
    items = [to_read(session, actor, e) for e in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.expense_date, last.created_at, last.id)
    return items, next_cursor


def get_summary(
    session: Session, actor: GroupActor, filters: ExpenseFilters, *, mine: bool = False
) -> SummaryRead:
    """Group spending, or with `mine` the actor's own share of it (personal expenses too)."""
    _check_range(filters)
    rows = erepo.summary(
        session, actor.group_id, filters, share_member_id=actor.member_id if mine else None
    )
    return SummaryRead(
        count=rows.count,
        total_cents=rows.total_cents,
        by_category=[CategoryTotalRead(category_id=c, total_cents=t) for c, t in rows.by_category],
        by_payer=[PayerTotalRead(member_id=m, total_cents=t) for m, t in rows.by_payer],
    )


def list_revisions(session: Session, actor: GroupActor, expense_id: UUID) -> list[RevisionRead]:
    _load(session, actor, expense_id)
    return [
        RevisionRead.model_validate(r) for r in erepo.revisions(session, actor.group_id, expense_id)
    ]


# ----------------------------------------------------------------- update


def _involved_members(
    session: Session, expense: Expense, before: dict[str, Any]
) -> frozenset[UUID]:
    """Payer and participants before and after a change: who an edit or deletion affects."""
    members = {expense.payer_member_id, UUID(before["payer_member_id"])}
    members.update(UUID(s["member_id"]) for s in before["shares"])
    members.update(s.member_id for s in _stored_shares(session, expense))
    return frozenset(members)


def _stored_spec(session: Session, expense: Expense) -> SplitSpec:
    """The expense's own split as an explicit spec (keeps its participants and inputs)."""
    stored = _stored_shares(session, expense)
    if expense.split_type == "equal" and not stored:
        return EqualSplit(split_type="equal")
    return spec_from_stored(expense.split_type, stored)


def update_expense(
    session: Session,
    actor: GroupActor,
    expense_id: UUID,
    data: ExpenseUpdate,
    if_match: int | None,
    *,
    notifier: Notifier = _NO_NOTIFIER,
) -> ExpenseRead:
    require_active(actor)
    lock_group_for_balance_write(session, actor.group_id)
    expense = _load(session, actor, expense_id, for_update=True)
    if expense.deleted_at is not None:
        raise NotFound("Expense not found")
    check_version(if_match, expense.version, current_body=to_read(session, actor, expense))
    _require_no_left_members(session, expense)
    fields = data.model_fields_set

    before = snapshot_json(session, expense)
    amount = data.amount_cents if data.amount_cents is not None else expense.amount_cents
    payer = data.payer_member_id or expense.payer_member_id
    category_id = data.category_id if "category_id" in fields else expense.category_id
    if "payer_member_id" in fields:
        _check_payer(session, actor.group_id, payer)
    if "category_id" in fields:
        _check_category(session, actor.group_id, category_id)

    resolution: Resolution | None = None
    if fields & {"split", "participants"}:
        # An explicit re-split: today's rules and active members.
        resolution = _resolve(
            session,
            actor.group_id,
            amount_cents=amount,
            payer_member_id=payer,
            category_id=category_id,
            split=data.split,
            participants=data.participants,
        )
    elif amount != expense.amount_cents or (
        payer != expense.payer_member_id and expense.split_type == "personal"
    ):
        # Same participants and inputs, new amount (or the personal expense's new payer).
        resolution = _resolve(
            session,
            actor.group_id,
            amount_cents=amount,
            payer_member_id=payer,
            category_id=category_id,
            split=_stored_spec(session, expense),
            participants=None,
        )
        resolution.split_origin = expense.split_origin
        resolution.participant_mode = expense.participant_mode
        resolution.rule_fallback = expense.rule_fallback

    expense.amount_cents = amount
    expense.payer_member_id = payer
    expense.category_id = category_id
    expense.expense_date = data.expense_date or expense.expense_date
    if data.description is not None:
        expense.description = data.description
    if "notes" in fields:
        expense.notes = data.notes
    if resolution is not None:
        _write_shares(session, expense, resolution)
    expense.version += 1
    expense.updated_by_user_id = actor.user_id
    session.flush()
    _revision(session, expense, "update", actor.user_id, before)
    session.commit()
    notifier.notify(
        NotificationEvent(
            "expense_updated",
            actor.group_id,
            actor.user_id,
            expense.id,
            _involved_members(session, expense, before),
        )
    )
    return to_read(session, actor, expense)


def delete_expense(
    session: Session,
    actor: GroupActor,
    expense_id: UUID,
    data: ExpenseDeleteIn,
    if_match: int | None,
    *,
    notifier: Notifier = _NO_NOTIFIER,
) -> None:
    require_active(actor)
    lock_group_for_balance_write(session, actor.group_id)
    expense = _load(session, actor, expense_id, for_update=True)
    if expense.deleted_at is not None:
        return
    check_version(if_match, expense.version, current_body=to_read(session, actor, expense))
    _require_no_left_members(session, expense)
    before = snapshot_json(session, expense)
    expense.deleted_at = clock.now()
    expense.deleted_reason = data.reason
    expense.version += 1
    expense.updated_by_user_id = actor.user_id
    session.flush()
    _revision(session, expense, "delete", actor.user_id, before, data.reason)
    session.commit()
    notifier.notify(
        NotificationEvent(
            "expense_deleted",
            actor.group_id,
            actor.user_id,
            expense.id,
            _involved_members(session, expense, before),
        )
    )
