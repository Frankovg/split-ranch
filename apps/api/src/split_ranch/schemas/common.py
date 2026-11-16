"""Shared Pydantic building blocks (strict, extra=forbid)."""

from datetime import date
from typing import Annotated, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# UUIDs and dates arrive as JSON strings: allow that coercion, keep everything else strict.
Id = Annotated[UUID, Field(strict=False)]
Day = Annotated[date, Field(strict=False)]
AmountCents = Annotated[int, Field(ge=1, le=100_000_000)]
Reason = Annotated[str, Field(min_length=5, max_length=280)]


class StrictModel(BaseModel):
    """Input model: unknown fields rejected, no implicit type coercion."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ReadModel(BaseModel):
    """Output model."""

    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class Page(ReadModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class ReasonIn(StrictModel):
    reason: Reason | None = None
