"""Running balance, payment suggestions and payments."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from split_ranch.schemas.common import AmountCents, Id, ReadModel, StrictModel

# Mirrors models.payments.PAYMENT_STATUSES (the DB check constraint).
PaymentStatus = Literal["sent", "confirmed", "disputed", "cancelled"]
# Mirrors models.payments.PAYMENT_METHODS.
PaymentMethod = Literal["bizum", "bank_transfer", "cash", "other"]


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
    method: PaymentMethod
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
    status: PaymentStatus
    # None only on payments recorded before the method was required.
    method: PaymentMethod | None
    note: str | None
    created_by_user_id: Id
    confirmed_at: datetime | None
    confirmed_by_user_id: Id | None
    version: int
    created_at: datetime
    updated_at: datetime
