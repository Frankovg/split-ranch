"""Expenses, revisions and the spending summary."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from split_ranch.schemas.common import (
    AmountCents,
    Day,
    Id,
    NonBlank,
    ReadModel,
    Reason,
    StrictModel,
)
from split_ranch.schemas.split import ShareRead, SplitSpec

ExpenseSource = Literal["manual", "ai_text", "ai_voice"]


class ExpenseCreate(StrictModel):
    # Client-generated id: retrying a create with the same id returns the stored expense.
    id: Id | None = None
    amount_cents: AmountCents
    description: NonBlank = Field(max_length=140)
    category_id: Id | None = None
    payer_member_id: Id
    expense_date: Day
    split: SplitSpec | None = None
    participants: list[Id] | None = Field(default=None, min_length=1, max_length=50)
    source: ExpenseSource = "manual"
    notes: str | None = Field(default=None, max_length=1000)


class ExpensePreviewIn(StrictModel):
    amount_cents: AmountCents
    category_id: Id | None = None
    payer_member_id: Id
    expense_date: Day
    split: SplitSpec | None = None
    participants: list[Id] | None = Field(default=None, min_length=1, max_length=50)


class ExpenseUpdate(StrictModel):
    """Only the fields sent change. Sending `split` or `participants` re-splits the expense
    with today's rules and members; any other edit keeps its participants and inputs."""

    amount_cents: AmountCents | None = None
    description: NonBlank | None = Field(default=None, max_length=140)
    category_id: Id | None = None
    payer_member_id: Id | None = None
    expense_date: Day | None = None
    split: SplitSpec | None = None
    participants: list[Id] | None = Field(default=None, min_length=1, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)


class ExpenseDeleteIn(StrictModel):
    reason: Reason | None = None


class ExpenseRead(ReadModel):
    id: Id
    group_id: Id
    version: int
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
    shares: list[ShareRead]
    created_by_user_id: Id | None
    updated_by_user_id: Id | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    can_edit: bool = False


class SplitPreviewRead(ReadModel):
    split_type: str
    split_origin: str
    participant_mode: str
    rule_fallback: bool
    shares: list[ShareRead]


class RevisionRead(ReadModel):
    id: Id
    version: int
    action: str
    actor_user_id: Id | None
    reason: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime


class CategoryTotalRead(ReadModel):
    # None = expenses without a category.
    category_id: Id | None
    total_cents: int


class PayerTotalRead(ReadModel):
    member_id: Id
    total_cents: int


class SummaryRead(ReadModel):
    """Totals of the live expenses matching the list filters.

    By default full amounts of shared (non-personal) expenses; with `mine=true` only the
    caller's share of each expense they take part in, personal expenses included.
    """

    count: int
    total_cents: int
    by_category: list[CategoryTotalRead]
    by_payer: list[PayerTotalRead]
