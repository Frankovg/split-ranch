"""Expenses: create, preview, read, list, update, delete, confirm, revisions, adjustments."""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from split_ranch.core import clock
from split_ranch.core.actor import HouseholdActor
from split_ranch.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from split_ranch.domain import DomainError
from split_ranch.models import Expense, ExpenseRevision, ExpenseShare, Household, Period
from split_ranch.repositories import expenses as erepo
from split_ranch.repositories import households as hrepo
from split_ranch.schemas.common import month_to_str
from split_ranch.schemas.expenses import (
    AdjustmentCreate,
    AdjustmentRead,
    ExpenseCreate,
    ExpenseDeleteIn,
    ExpensePreviewIn,
    ExpenseRead,
    ExpenseUpdate,
    PeriodRef,
    RevisionRead,
    SplitPreviewRead,
)
from split_ranch.schemas.split import EqualSplit, ShareRead, SplitSpec
from split_ranch.use_cases import idempotency
from split_ranch.use_cases.common import check_version, require_active
from split_ranch.use_cases.periods import (
    after_edit_in_closed_period,
    get_or_create_period,
    period_state,
)
from split_ranch.use_cases.split_resolution import (
    Resolution,
    ResolvedShare,
    RuleData,
    RuleRow,
    resolve_expense_split,
    spec_from_stored,
)

DEFAULT_PAGE = 50
MAX_PAGE = 200


# ---------------------------------------------------------------- helpers


def _household(session: Session, household_id: UUID) -> Household:
    household = hrepo.get_household(session, household_id)
    if household is None:
        raise NotFound("Household not found")
    return household


def _rule_data(
    session: Session, household_id: UUID, scope: str, category_id: UUID | None = None
) -> RuleData | None:
    if scope == "category" and category_id is None:
        return None
    rule = hrepo.get_rule(session, household_id, scope, category_id)
    if rule is None:
        return None
    rows = [
        RuleRow(s.member_id, s.weight, s.basis_points, s.amount_cents)
        for s in hrepo.rule_shares(session, household_id, rule.id)
    ]
    return RuleData(rule.split_type, rows)


def _resolve(
    session: Session,
    household_id: UUID,
    *,
    month: date,
    amount_cents: int,
    payer_member_id: UUID,
    category_id: UUID | None,
    split: SplitSpec | None,
    participants: Sequence[UUID] | None,
    allowed_members: set[UUID] | None = None,
) -> Resolution:
    members = hrepo.list_members(session, household_id)
    period_ids = [m.id for m in hrepo.period_members(session, household_id, month)]
    return resolve_expense_split(
        amount_cents=amount_cents,
        payer_member_id=payer_member_id,
        override=split,
        participants=participants,
        category_rule=_rule_data(session, household_id, "category", category_id),
        default_rule=_rule_data(session, household_id, "household_default"),
        period_members=period_ids,
        canonical_order=[m.id for m in members],
        allowed_members=allowed_members,
    )


def _check_payer(session: Session, household_id: UUID, payer_id: UUID, month: date) -> None:
    member = hrepo.get_member(session, household_id, payer_id)
    if member is None:
        raise Unprocessable("Payer is not a member of this household", code="invalid_payer")
    in_period = member.joined_period <= month and (
        member.left_period is None or member.left_period >= month
    )
    if member.status == "left" or not in_period:
        raise Unprocessable("Payer does not take part in this period", code="invalid_payer")


def _check_category(session: Session, household_id: UUID, category_id: UUID | None) -> None:
    if category_id is None:
        return
    if hrepo.get_category(session, household_id, category_id, include_archived=False) is None:
        raise Unprocessable("Unknown or archived category", code="invalid_category")


def _write_shares(session: Session, expense: Expense, resolution: Resolution) -> None:
    session.execute(
        delete(ExpenseShare).where(
            ExpenseShare.household_id == expense.household_id,
            ExpenseShare.expense_id == expense.id,
        )
    )
    for i, s in enumerate(resolution.shares):
        session.add(
            ExpenseShare(
                expense_id=expense.id,
                household_id=expense.household_id,
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
    rows = erepo.shares_for(session, expense.household_id, [expense.id]).get(expense.id, [])
    return [
        ResolvedShare(s.member_id, s.amount_cents, s.weight, s.basis_points, s.exact_cents)
        for s in rows
    ]


def snapshot_json(session: Session, expense: Expense) -> dict[str, Any]:
    """Expense state stored in revisions (shares included)."""
    return {
        "id": str(expense.id),
        "period_id": str(expense.period_id),
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
        "status": expense.status,
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
        ExpenseRevision(
            expense_id=expense.id,
            household_id=expense.household_id,
            version=expense.version,
            action=action,
            actor_user_id=actor_user_id,
            reason=reason,
            before=before,
            after=snapshot_json(session, expense),
        )
    )


def _can_edit(actor: HouseholdActor, expense: Expense) -> bool:
    return actor.status != "left" and (
        actor.is_admin or expense.created_by_user_id == actor.user_id
    )


def to_read(
    session: Session,
    actor: HouseholdActor,
    expense: Expense,
    *,
    period: Period | None = None,
    state_cache: dict[UUID, str] | None = None,
) -> ExpenseRead:
    if period is None:
        period = erepo.get_period(session, expense.household_id, expense.period_id)
        assert period is not None
    if state_cache is not None and period.id in state_cache:
        state = state_cache[period.id]
    else:
        state = period_state(session, period)
        if state_cache is not None:
            state_cache[period.id] = state
    return ExpenseRead(
        id=expense.id,
        household_id=expense.household_id,
        version=expense.version,
        period=PeriodRef(id=period.id, month=month_to_str(period.month), status=period.status),
        category_id=expense.category_id,
        payer_member_id=expense.payer_member_id,
        amount_cents=expense.amount_cents,
        currency=expense.currency,
        description=expense.description,
        notes=expense.notes,
        expense_date=expense.expense_date,
        split_type=expense.split_type,
        split_origin=expense.split_origin,
        participant_mode=expense.participant_mode,
        rule_fallback=expense.rule_fallback,
        status=expense.status,
        source=expense.source,
        adjusts_expense_id=expense.adjusts_expense_id,
        shares=[
            ShareRead(
                member_id=s.member_id,
                amount_cents=s.amount_cents,
                weight=s.weight,
                basis_points=s.basis_points,
                exact_cents=s.exact_cents,
            )
            for s in _stored_shares(session, expense)
        ],
        created_by_user_id=expense.created_by_user_id,
        created_at=expense.created_at,
        updated_at=expense.updated_at,
        deleted_at=expense.deleted_at,
        can_edit=expense.deleted_at is None and _can_edit(actor, expense),
        edit_requires_reason=state == "closed",
        edit_mode="adjustment" if state == "locked" else "in_place",
    )


def _load_visible(
    session: Session, actor: HouseholdActor, expense_id: UUID, *, for_update: bool = False
) -> Expense:
    expense = erepo.get_expense(session, actor.household_id, expense_id, for_update=for_update)
    if expense is None or (
        expense.status == "draft" and expense.created_by_user_id != actor.user_id
    ):
        raise NotFound("Expense not found")
    return expense


def _require_edit_rights(actor: HouseholdActor, expense: Expense) -> None:
    require_active(actor)
    if not _can_edit(actor, expense):
        raise Forbidden("Only the author or an admin can change this expense")


def _gate_period(state: str, reason: str | None, *, extra: dict[str, Any] | None = None) -> None:
    """Editing rules per period state (docs/03 §4)."""
    if state == "locked":
        raise Conflict(
            "The period has payments; create an adjustment in the current period instead",
            code="period_locked",
            extra=extra,
        )
    if state == "closed" and not reason:
        raise Conflict("A reason is required to change a closed period", code="reason_required")


# ----------------------------------------------------------------- create


def preview_split(
    session: Session, actor: HouseholdActor, data: ExpensePreviewIn
) -> SplitPreviewRead:
    month = clock.month_start(data.expense_date)
    _check_payer(session, actor.household_id, data.payer_member_id, month)
    _check_category(session, actor.household_id, data.category_id)
    res = _resolve(
        session,
        actor.household_id,
        month=month,
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
        shares=[ShareRead(**s.__dict__) for s in res.shares],
    )


@dataclass(frozen=True)
class CreateResult:
    status: int
    body: dict[str, Any]
    version: int


def create_expense(
    session: Session,
    actor: HouseholdActor,
    data: ExpenseCreate,
    *,
    idempotency_key: str | None = None,
    trusted_source: bool = False,
) -> CreateResult:
    """Create an expense. Public clients may only use `source='manual'`."""
    require_active(actor)
    if data.source != "manual" and not trusted_source:
        raise Unprocessable("Only manual expenses can be created by clients", code="invalid_source")

    endpoint = f"POST /households/{actor.household_id}/expenses"
    payload_hash = idempotency.request_hash(data.model_dump(mode="json"))
    replay = idempotency.lookup(session, actor.user_id, idempotency_key, endpoint, payload_hash)
    if replay is not None:
        return CreateResult(replay.status, replay.body, int(replay.body.get("version", 1)))

    if data.id is not None:
        existing = erepo.get_expense(session, actor.household_id, data.id)
        if existing is not None:
            same = (
                existing.created_by_user_id == actor.user_id
                and existing.amount_cents == data.amount_cents
                and existing.description == data.description
                and existing.payer_member_id == data.payer_member_id
                and existing.expense_date == data.expense_date
            )
            if not same:
                raise Conflict("An expense with this id already exists", code="id_conflict")
            body = to_read(session, actor, existing).model_dump(mode="json")
            return CreateResult(200, body, existing.version)
        if erepo.expense_exists_anywhere(session, data.id):
            raise Conflict("An expense with this id already exists", code="id_conflict")

    household = _household(session, actor.household_id)
    month = clock.month_start(data.expense_date)
    period = get_or_create_period(session, household, month)
    state = period_state(session, period)
    _gate_period(state, data.reason)
    _check_payer(session, household.id, data.payer_member_id, month)
    _check_category(session, household.id, data.category_id)
    resolution = _resolve(
        session,
        household.id,
        month=month,
        amount_cents=data.amount_cents,
        payer_member_id=data.payer_member_id,
        category_id=data.category_id,
        split=data.split,
        participants=data.participants,
    )
    expense = Expense(
        household_id=household.id,
        period_id=period.id,
        category_id=data.category_id,
        payer_member_id=data.payer_member_id,
        amount_cents=data.amount_cents,
        currency=data.currency,
        description=data.description.strip(),
        notes=data.notes,
        expense_date=data.expense_date,
        split_type=resolution.split_type,
        split_origin=resolution.split_origin,
        status=data.status,
        source=data.source,
        source_transcript=data.source_transcript,
        created_by_user_id=actor.user_id,
        updated_by_user_id=actor.user_id,
        version=1,
    )
    if data.id is not None:
        expense.id = data.id
    session.add(expense)
    session.flush()
    _write_shares(session, expense, resolution)
    _revision(session, expense, "create", actor.user_id, None, data.reason)
    if state == "closed" and expense.status == "confirmed":
        after_edit_in_closed_period(session, household, period)
    session.flush()
    body = to_read(session, actor, expense, period=period).model_dump(mode="json")
    idempotency.store(session, actor.user_id, idempotency_key, endpoint, payload_hash, 201, body)
    session.commit()
    return CreateResult(201, body, expense.version)


# ------------------------------------------------------------------ reads


def get_expense(session: Session, actor: HouseholdActor, expense_id: UUID) -> ExpenseRead:
    expense = _load_visible(session, actor, expense_id)
    return to_read(session, actor, expense)


def _encode_cursor(d: date, i: UUID) -> str:
    raw = json.dumps({"d": d.isoformat(), "i": str(i)}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[date, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return date.fromisoformat(data["d"]), UUID(data["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise Unprocessable("Invalid cursor") from exc


def list_expenses(
    session: Session,
    actor: HouseholdActor,
    *,
    limit: int = DEFAULT_PAGE,
    cursor: str | None = None,
    month: date | None = None,
    category_id: UUID | None = None,
    payer_member_id: UUID | None = None,
    q: str | None = None,
    status: str | None = None,
) -> tuple[list[ExpenseRead], str | None]:
    limit = max(1, min(limit, MAX_PAGE))
    period_id: UUID | None = None
    if month is not None:
        period = erepo.get_period_by_month(session, actor.household_id, month)
        if period is None:
            return [], None
        period_id = period.id
    rows = erepo.list_expenses(
        session,
        actor.household_id,
        viewer_user_id=actor.user_id,
        limit=limit + 1,
        after=_decode_cursor(cursor) if cursor else None,
        period_id=period_id,
        category_id=category_id,
        payer_member_id=payer_member_id,
        q=q,
        status=status,
    )
    cache: dict[UUID, str] = {}
    items = [to_read(session, actor, e, state_cache=cache) for e in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.expense_date, last.id)
    return items, next_cursor


def list_revisions(session: Session, actor: HouseholdActor, expense_id: UUID) -> list[RevisionRead]:
    _load_visible(session, actor, expense_id)
    return [
        RevisionRead.model_validate(r)
        for r in erepo.revisions(session, actor.household_id, expense_id)
    ]


# ----------------------------------------------------------------- update


def _resolve_for_existing(
    session: Session,
    expense: Expense,
    *,
    month: date,
    amount_cents: int,
    payer_member_id: UUID,
    category_id: UUID | None,
    split: SplitSpec | None,
    participants: Sequence[UUID] | None,
    allowed_members: set[UUID] | None = None,
) -> Resolution:
    """Re-resolve: explicit input wins; an earlier override is kept; else the rule chain."""
    if split is None and participants is None and expense.split_origin == "override":
        if expense.participant_mode == "all" and expense.split_type == "equal":
            split = EqualSplit(split_type="equal")
        else:
            split = spec_from_stored(expense.split_type, _stored_shares(session, expense))
    res = _resolve(
        session,
        expense.household_id,
        month=month,
        amount_cents=amount_cents,
        payer_member_id=payer_member_id,
        category_id=category_id,
        split=split,
        participants=participants,
        allowed_members=allowed_members,
    )
    return res


def _adjustment_preview(
    session: Session, actor: HouseholdActor, expense: Expense, data: ExpenseUpdate | None
) -> dict[str, Any]:
    reversal = [
        {"member_id": str(s.member_id), "amount_cents": -s.amount_cents}
        for s in _stored_shares(session, expense)
    ]
    preview: dict[str, Any] = {
        "reversal": {"amount_cents": -expense.amount_cents, "shares": reversal},
        "correction": None,
    }
    if data is not None:
        try:
            fields = data.model_fields_set
            res = _resolve_for_existing(
                session,
                expense,
                month=clock.month_start(
                    clock.today_in(_household(session, expense.household_id).timezone)
                ),
                amount_cents=data.amount_cents
                if data.amount_cents is not None
                else expense.amount_cents,
                payer_member_id=data.payer_member_id or expense.payer_member_id,
                category_id=data.category_id if "category_id" in fields else expense.category_id,
                split=data.split,
                participants=data.participants,
                allowed_members=_shares_members(session, expense),
            )
            preview["correction"] = {
                "amount_cents": data.amount_cents or expense.amount_cents,
                "shares": [
                    {"member_id": str(s.member_id), "amount_cents": s.amount_cents}
                    for s in res.shares
                ],
            }
        except DomainError:
            preview["correction"] = None
    return preview


def _shares_members(session: Session, expense: Expense) -> set[UUID]:
    return {s.member_id for s in _stored_shares(session, expense)} | {expense.payer_member_id}


def update_expense(
    session: Session,
    actor: HouseholdActor,
    expense_id: UUID,
    data: ExpenseUpdate,
    if_match: int | None,
) -> ExpenseRead:
    expense = _load_visible(session, actor, expense_id, for_update=True)
    if expense.deleted_at is not None:
        raise NotFound("Expense not found")
    _require_edit_rights(actor, expense)
    check_version(if_match, expense.version, current_body=to_read(session, actor, expense))
    household = _household(session, actor.household_id)
    fields = data.model_fields_set

    old_period = erepo.get_period(session, household.id, expense.period_id, for_update=True)
    assert old_period is not None
    new_date = data.expense_date or expense.expense_date
    new_month = clock.month_start(new_date)
    new_period = (
        old_period
        if new_month == old_period.month
        else get_or_create_period(session, household, new_month)
    )
    states = {
        old_period.id: period_state(session, old_period),
        new_period.id: period_state(session, new_period),
    }
    for state in states.values():
        _gate_period(
            state,
            data.reason,
            extra={"adjustment_preview": _adjustment_preview(session, actor, expense, data)}
            if state == "locked"
            else None,
        )

    before = snapshot_json(session, expense)
    amount = data.amount_cents if data.amount_cents is not None else expense.amount_cents
    payer = data.payer_member_id or expense.payer_member_id
    category_id = data.category_id if "category_id" in fields else expense.category_id
    if "payer_member_id" in fields or new_period.id != old_period.id:
        _check_payer(session, household.id, payer, new_month)
    if "category_id" in fields:
        _check_category(session, household.id, category_id)

    needs_resolve = (
        bool(fields & {"amount_cents", "payer_member_id", "category_id", "split", "participants"})
        or new_period.id != old_period.id
    )
    if needs_resolve:
        resolution = _resolve_for_existing(
            session,
            expense,
            month=new_month,
            amount_cents=amount,
            payer_member_id=payer,
            category_id=category_id,
            split=data.split,
            participants=data.participants,
        )
    expense.amount_cents = amount
    expense.payer_member_id = payer
    expense.category_id = category_id
    expense.expense_date = new_date
    expense.period_id = new_period.id
    if data.description is not None:
        expense.description = data.description.strip()
    if "notes" in fields:
        expense.notes = data.notes
    if needs_resolve:
        _write_shares(session, expense, resolution)
    expense.version += 1
    expense.updated_by_user_id = actor.user_id
    session.flush()
    _revision(session, expense, "update", actor.user_id, before, data.reason)
    if expense.status == "confirmed":
        for period in {old_period.id: old_period, new_period.id: new_period}.values():
            if states[period.id] == "closed":
                after_edit_in_closed_period(session, household, period)
    session.commit()
    return to_read(session, actor, expense, period=new_period)


def delete_expense(
    session: Session,
    actor: HouseholdActor,
    expense_id: UUID,
    data: ExpenseDeleteIn,
    if_match: int | None,
) -> None:
    expense = _load_visible(session, actor, expense_id, for_update=True)
    if expense.deleted_at is not None:
        return
    _require_edit_rights(actor, expense)
    check_version(if_match, expense.version, current_body=to_read(session, actor, expense))
    household = _household(session, actor.household_id)
    period = erepo.get_period(session, household.id, expense.period_id, for_update=True)
    assert period is not None
    state = period_state(session, period)
    _gate_period(
        state,
        data.reason,
        extra={"adjustment_preview": _adjustment_preview(session, actor, expense, None)}
        if state == "locked"
        else None,
    )
    before = snapshot_json(session, expense)
    expense.deleted_at = clock.now()
    expense.deleted_reason = data.reason
    expense.version += 1
    expense.updated_by_user_id = actor.user_id
    session.flush()
    _revision(session, expense, "delete", actor.user_id, before, data.reason)
    if state == "closed" and expense.status == "confirmed":
        after_edit_in_closed_period(session, household, period)
    session.commit()


def confirm_draft(
    session: Session,
    actor: HouseholdActor,
    expense_id: UUID,
    reason: str | None,
    if_match: int | None,
) -> ExpenseRead:
    expense = _load_visible(session, actor, expense_id, for_update=True)
    if expense.deleted_at is not None:
        raise NotFound("Expense not found")
    _require_edit_rights(actor, expense)
    check_version(if_match, expense.version, current_body=to_read(session, actor, expense))
    if expense.status != "draft":
        raise Conflict("Expense is not a draft", code="not_draft")
    household = _household(session, actor.household_id)
    period = erepo.get_period(session, household.id, expense.period_id, for_update=True)
    assert period is not None
    state = period_state(session, period)
    _gate_period(state, reason)
    before = snapshot_json(session, expense)
    expense.status = "confirmed"
    expense.version += 1
    expense.updated_by_user_id = actor.user_id
    session.flush()
    _revision(session, expense, "confirm", actor.user_id, before, reason)
    if state == "closed":
        after_edit_in_closed_period(session, household, period)
    session.commit()
    return to_read(session, actor, expense, period=period)


# ------------------------------------------------------------ adjustments


def create_adjustment(
    session: Session, actor: HouseholdActor, expense_id: UUID, data: AdjustmentCreate
) -> AdjustmentRead:
    """Correct an expense of a locked/settled period with reversal + correction rows
    in the current open period (docs/03 "Adjustments")."""
    original = _load_visible(session, actor, expense_id, for_update=True)
    if original.deleted_at is not None or original.status != "confirmed":
        raise NotFound("Expense not found")
    _require_edit_rights(actor, original)
    household = _household(session, actor.household_id)
    source_period = erepo.get_period(session, household.id, original.period_id)
    assert source_period is not None
    if period_state(session, source_period) != "locked":
        raise Conflict(
            "The period is not locked: edit the expense in place", code="period_not_locked"
        )

    today = clock.today_in(household.timezone)
    target = get_or_create_period(session, household, clock.month_start(today))
    if period_state(session, target) != "open":
        raise Conflict("The current period is not open", code="period_locked")

    stored = _stored_shares(session, original)
    personal = original.split_type == "personal"
    reversal = Expense(
        household_id=household.id,
        period_id=target.id,
        category_id=original.category_id,
        payer_member_id=original.payer_member_id,
        amount_cents=-original.amount_cents,
        description=original.description,
        notes=data.reason,
        expense_date=today,
        split_type="personal" if personal else "exact",
        split_origin="override",
        participant_mode="subset",
        status="confirmed",
        source="adjustment",
        adjusts_expense_id=original.id,
        created_by_user_id=actor.user_id,
        updated_by_user_id=actor.user_id,
        version=1,
    )
    session.add(reversal)
    session.flush()
    # Exact negation of the stored shares: no re-allocation, cancels X to the cent.
    _write_shares(
        session,
        reversal,
        Resolution(
            reversal.split_type,
            "override",
            "subset",
            False,
            [
                ResolvedShare(s.member_id, -s.amount_cents, exact_cents=-s.amount_cents)
                for s in stored
            ],
        ),
    )
    _revision(session, reversal, "create", actor.user_id, None, data.reason)

    correction: Expense | None = None
    if not data.delete:
        fields = data.model_fields_set
        amount = data.amount_cents if data.amount_cents is not None else original.amount_cents
        payer = data.payer_member_id or original.payer_member_id
        category_id = data.category_id if "category_id" in fields else original.category_id
        if "category_id" in fields:
            _check_category(session, household.id, category_id)
        split = data.split
        if split is None and data.participants is None:
            # Re-apply the split that the original expense used.
            if original.split_type == "equal" and original.participant_mode == "all":
                split = EqualSplit(split_type="equal")
            else:
                split = spec_from_stored(original.split_type, stored)
        resolution = _resolve(
            session,
            household.id,
            month=target.month,
            amount_cents=amount,
            payer_member_id=payer,
            category_id=category_id,
            split=split,
            participants=data.participants,
            allowed_members=_shares_members(session, original) | {payer},
        )
        if data.split is None and data.participants is None:
            resolution.split_origin = original.split_origin
            resolution.participant_mode = original.participant_mode
        correction = Expense(
            household_id=household.id,
            period_id=target.id,
            category_id=category_id,
            payer_member_id=payer,
            amount_cents=amount,
            description=(data.description or original.description).strip(),
            notes=data.notes if data.notes is not None else original.notes,
            expense_date=today,
            split_type=resolution.split_type,
            split_origin=resolution.split_origin,
            status="confirmed",
            source="adjustment",
            adjusts_expense_id=original.id,
            created_by_user_id=actor.user_id,
            updated_by_user_id=actor.user_id,
            version=1,
        )
        session.add(correction)
        session.flush()
        _write_shares(session, correction, resolution)
        _revision(session, correction, "create", actor.user_id, None, data.reason)

    session.commit()
    return AdjustmentRead(
        reversal=to_read(session, actor, reversal, period=target),
        correction=to_read(session, actor, correction, period=target) if correction else None,
    )


# ------------------------------------------------------- rule re-resolution


def reresolve_open_expenses(
    session: Session,
    household_id: UUID,
    *,
    actor_user_id: UUID | None,
    reason: str,
    only_all_members: bool = False,
    split_origin: str | None = None,
    category_id: UUID | None = None,
) -> int:
    """Re-resolve open-period expenses after a rule change or a member joining.

    Closed periods are never touched. Returns the number of expenses changed.
    """
    changed = 0
    for expense in erepo.open_period_expenses(session, household_id, split_origin=split_origin):
        if expense.source == "adjustment":
            continue
        if only_all_members and expense.participant_mode != "all":
            continue
        if category_id is not None and expense.category_id != category_id:
            continue
        if split_origin is None and not only_all_members and expense.split_origin == "override":
            continue
        month = clock.month_start(expense.expense_date)
        before_shares = [(s.member_id, s.amount_cents) for s in _stored_shares(session, expense)]
        try:
            res = _resolve_for_existing(
                session,
                expense,
                month=month,
                amount_cents=expense.amount_cents,
                payer_member_id=expense.payer_member_id,
                category_id=expense.category_id,
                split=None,
                participants=None,
            )
        except DomainError:
            continue
        after_shares = [(s.member_id, s.amount_cents) for s in res.shares]
        if after_shares == before_shares and res.split_origin == expense.split_origin:
            continue
        before = snapshot_json(session, expense)
        _write_shares(session, expense, res)
        expense.version += 1
        expense.updated_by_user_id = actor_user_id
        session.flush()
        _revision(session, expense, "update", actor_user_id, before, reason)
        changed += 1
    return changed
