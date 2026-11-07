"""Quick splits payloads."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from split_ranch.schemas.common import AmountCents, Id, ReadModel, StrictModel


class QuickParticipantIn(StrictModel):
    id: Id
    name: str = Field(min_length=1, max_length=40)
    sort_key: int = Field(default=0, ge=0, le=10_000)
    weight: int = Field(default=1, ge=0, le=1_000_000)


class QuickShareIn(StrictModel):
    participant_id: Id
    weight: int | None = Field(default=None, ge=0, le=1_000_000)
    exact_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    # Client-computed amount; the server recomputes and rejects mismatches.
    amount_cents: int = Field(ge=0, le=100_000_000)


class QuickExpenseIn(StrictModel):
    id: Id
    payer_participant_id: Id | None = None
    amount_cents: AmountCents
    description: str | None = Field(default=None, max_length=140)
    split_type: Literal["equal", "weights", "exact"]
    shares: list[QuickShareIn] = Field(min_length=1, max_length=50)


class QuickTransferIn(StrictModel):
    from_participant_id: Id
    to_participant_id: Id
    amount_cents: int = Field(ge=1, le=100_000_000)


class QuickEventIn(StrictModel):
    title: str = Field(min_length=1, max_length=80)
    mode: Literal["total", "itemised"]
    currency: Literal["EUR"] = "EUR"
    participants: list[QuickParticipantIn] = Field(min_length=1, max_length=50)
    expenses: list[QuickExpenseIn] = Field(default_factory=list, max_length=200)
    # Optional client-computed transfers, checked against the server's result.
    transfers: list[QuickTransferIn] | None = None

    @model_validator(mode="after")
    def _unique(self) -> "QuickEventIn":
        ids = [p.id for p in self.participants]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate participant id")
        names = [p.name.strip().lower() for p in self.participants]
        if len(set(names)) != len(names):
            raise ValueError("duplicate participant name")
        expense_ids = [e.id for e in self.expenses]
        if len(set(expense_ids)) != len(expense_ids):
            raise ValueError("duplicate expense id")
        return self


class QuickParticipantRead(ReadModel):
    id: Id
    name: str
    sort_key: int
    weight: int


class QuickShareRead(ReadModel):
    participant_id: Id
    weight: int | None
    exact_cents: int | None
    amount_cents: int


class QuickExpenseRead(ReadModel):
    id: Id
    payer_participant_id: Id | None
    amount_cents: int
    description: str | None
    split_type: str
    shares: list[QuickShareRead]


class QuickBalanceRead(ReadModel):
    participant_id: Id
    paid_cents: int
    owed_cents: int
    net_cents: int


class QuickTransferRead(ReadModel):
    from_participant_id: Id
    to_participant_id: Id
    amount_cents: int


class QuickEventRead(ReadModel):
    id: Id
    title: str
    mode: str
    currency: str
    version: int
    participants: list[QuickParticipantRead]
    expenses: list[QuickExpenseRead]
    balances: list[QuickBalanceRead]
    transfers: list[QuickTransferRead]
    share_token: str | None
    share_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class QuickEventSummary(ReadModel):
    id: Id
    title: str
    mode: str
    total_cents: int
    participant_count: int
    version: int
    updated_at: datetime


class QuickShareLinkRead(ReadModel):
    share_token: str
    url: str
    expires_at: datetime


class SharedQuickEventRead(ReadModel):
    """Public view: names and amounts only."""

    title: str
    currency: str
    participants: list[str]
    expenses: list[dict[str, object]]
    balances: list[dict[str, object]]
    transfers: list[dict[str, object]]
