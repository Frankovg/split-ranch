"""Running balance, payment suggestions and payments."""

from datetime import datetime

from pydantic import Field

from split_ranch.schemas.common import AmountCents, Id, ReadModel, StrictModel


class BalanceRead(ReadModel):
    member_id: Id
    paid_cents: int
    owed_cents: int
    # Confirmed balance: expenses plus confirmed payments. Σ net = 0.
    net_cents: int
    # Payments recorded as sent and not yet confirmed.
    pending_out_cents: int = 0
    pending_in_cents: int = 0


class SuggestionRead(ReadModel):
    from_member_id: Id
    to_member_id: Id
    amount_cents: int


class GroupBalanceRead(ReadModel):
    balances: list[BalanceRead]
    suggestions: list[SuggestionRead]


class PaymentCreate(StrictModel):
    # Client-generated id: retrying the same payment returns the stored one.
    id: Id
    from_member_id: Id
    to_member_id: Id
    amount_cents: AmountCents
    note: str | None = Field(default=None, max_length=280)


class PaymentNote(StrictModel):
    note: str | None = Field(default=None, max_length=280)


class PaymentDispute(StrictModel):
    note: str = Field(min_length=1, max_length=280)


class PaymentRead(ReadModel):
    id: Id
    group_id: Id
    from_member_id: Id
    to_member_id: Id
    amount_cents: int
    status: str
    note: str | None
    created_by_user_id: Id
    confirmed_at: datetime | None
    confirmed_by_user_id: Id | None
    version: int
    created_at: datetime
    updated_at: datetime
