"""Expenses, periods, balances and settlement."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from split_ranch.schemas.common import (
    AmountCents,
    Day,
    Id,
    PeriodSeq,
    ReadModel,
    Reason,
    StrictModel,
)
from split_ranch.schemas.split import ShareRead, SplitSpec

ExpenseSource = Literal["manual", "ai_text", "ai_voice", "recurring"]


class ExpenseCreate(StrictModel):
    # Client-generated id: retrying a create with the same id returns the stored expense.
    id: Id | None = None
    amount_cents: AmountCents
    description: str = Field(min_length=1, max_length=140)
    category_id: Id | None = None
    payer_member_id: Id
    expense_date: Day
    split: SplitSpec | None = None
    participants: list[Id] | None = Field(default=None, min_length=1, max_length=50)
    source: ExpenseSource = "manual"
    notes: str | None = Field(default=None, max_length=1000)
    # Default: the open period. A closed (unlocked) one needs a `reason`.
    period_seq: PeriodSeq | None = None
    reason: Reason | None = None


class ExpensePreviewIn(StrictModel):
    amount_cents: AmountCents
    category_id: Id | None = None
    payer_member_id: Id
    expense_date: Day
    split: SplitSpec | None = None
    participants: list[Id] | None = Field(default=None, min_length=1, max_length=50)
    period_seq: PeriodSeq | None = None


class ExpenseUpdate(StrictModel):
    amount_cents: AmountCents | None = None
    description: str | None = Field(default=None, min_length=1, max_length=140)
    category_id: Id | None = None
    payer_member_id: Id | None = None
    expense_date: Day | None = None
    split: SplitSpec | None = None
    participants: list[Id] | None = Field(default=None, min_length=1, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)
    reason: Reason | None = None


class ExpenseDeleteIn(StrictModel):
    reason: Reason | None = None


class AdjustmentCreate(StrictModel):
    """Correction of an expense in a locked/settled period (or `delete: true`)."""

    delete: bool = False
    amount_cents: AmountCents | None = None
    description: str | None = Field(default=None, min_length=1, max_length=140)
    category_id: Id | None = None
    payer_member_id: Id | None = None
    split: SplitSpec | None = None
    participants: list[Id] | None = Field(default=None, min_length=1, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)
    reason: Reason


class PeriodRef(ReadModel):
    id: Id
    seq: int
    status: str


class ExpenseRead(ReadModel):
    id: Id
    household_id: Id
    version: int
    period: PeriodRef
    category_id: Id | None
    payer_member_id: Id
    amount_cents: int
    description: str
    notes: str | None
    expense_date: date
    split_type: str
    split_origin: str
    participant_mode: str
    rule_fallback: bool
    source: str
    adjusts_expense_id: Id | None
    shares: list[ShareRead]
    created_by_user_id: Id | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    can_edit: bool = False
    edit_requires_reason: bool = False
    edit_mode: Literal["in_place", "adjustment"] = "in_place"


class SplitPreviewRead(ReadModel):
    split_type: str
    split_origin: str
    participant_mode: str
    rule_fallback: bool
    shares: list[ShareRead]


class AdjustmentRead(ReadModel):
    reversal: ExpenseRead
    correction: ExpenseRead | None


class RevisionRead(ReadModel):
    id: Id
    version: int
    action: str
    actor_user_id: Id | None
    reason: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime


# ---------------------------------------------------------------- periods


class BalanceRead(ReadModel):
    member_id: Id
    paid_cents: int
    owed_cents: int
    net_cents: int


class TransferRead(ReadModel):
    id: Id
    from_member_id: Id
    to_member_id: Id
    amount_cents: int
    status: str
    note: str | None
    sent_at: datetime | None
    confirmed_at: datetime | None
    version: int


class PeriodRead(ReadModel):
    id: Id
    seq: int
    status: str
    started_at: datetime
    closed_at: datetime | None
    settled_at: datetime | None
    reopened_count: int
    version: int
    total_cents: int = 0
    totals_by_category: list[dict[str, Any]] = Field(default_factory=list)
    locked: bool = False


class PeriodBalanceRead(ReadModel):
    period: PeriodRead
    balances: list[BalanceRead]


class SettlementRead(ReadModel):
    """The period's live transfers (cancelled ones are left out)."""

    period: PeriodRead
    transfers: list[TransferRead]


class ReopenIn(StrictModel):
    reason: Reason


class TransferSentIn(StrictModel):
    note: str | None = Field(default=None, max_length=280)


class TransferConfirmIn(StrictModel):
    note: str | None = Field(default=None, max_length=280)


class TransferDisputeIn(StrictModel):
    note: str = Field(min_length=1, max_length=280)
