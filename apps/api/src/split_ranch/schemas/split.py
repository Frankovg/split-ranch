"""Split specification: discriminated union on `split_type`.

Shared by group rules, expense overrides and (future) AI tools.
"""

from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter, model_validator

from split_ranch.domain import BASIS_POINTS_TOTAL
from split_ranch.schemas.common import Id, ReadModel, StrictModel


class MemberRef(StrictModel):
    member_id: Id


class WeightShare(StrictModel):
    member_id: Id
    weight: int = Field(ge=0, le=1_000_000)


class BasisPointsShare(StrictModel):
    member_id: Id
    basis_points: int = Field(ge=0, le=BASIS_POINTS_TOTAL)


class ExactShare(StrictModel):
    member_id: Id
    amount_cents: int = Field(ge=0, le=100_000_000)


def _unique(ids: list[object]) -> None:
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate member_id")


class EqualSplit(StrictModel):
    split_type: Literal["equal"]
    # None or empty = every active member of the group.
    shares: list[MemberRef] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _check(self) -> "EqualSplit":
        _unique([s.member_id for s in self.shares or []])
        return self


class WeightsSplit(StrictModel):
    split_type: Literal["weights"]
    shares: list[WeightShare] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _check(self) -> "WeightsSplit":
        _unique([s.member_id for s in self.shares])
        if all(s.weight == 0 for s in self.shares):
            raise ValueError("at least one weight must be positive")
        return self


class PercentagesSplit(StrictModel):
    split_type: Literal["percentages"]
    shares: list[BasisPointsShare] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _check(self) -> "PercentagesSplit":
        _unique([s.member_id for s in self.shares])
        return self


class ExactSplit(StrictModel):
    split_type: Literal["exact"]
    shares: list[ExactShare] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _check(self) -> "ExactSplit":
        _unique([s.member_id for s in self.shares])
        return self


class SingleSplit(StrictModel):
    split_type: Literal["single"]
    shares: list[MemberRef] = Field(min_length=1, max_length=1)


class PersonalSplit(StrictModel):
    split_type: Literal["personal"]


SplitSpec = Annotated[
    EqualSplit | WeightsSplit | PercentagesSplit | ExactSplit | SingleSplit | PersonalSplit,
    Field(discriminator="split_type"),
]


class ShareRead(ReadModel):
    member_id: Id
    amount_cents: int
    weight: int | None = None
    basis_points: int | None = None
    exact_cents: int | None = None


class CategoryRuleRead(ReadModel):
    category_id: Id
    split: SplitSpec


class SplitRulesRead(ReadModel):
    default: SplitSpec
    categories: list[CategoryRuleRead]


_SPEC_ADAPTER: TypeAdapter[SplitSpec] = TypeAdapter(SplitSpec)


def spec_to_json(spec: SplitSpec) -> dict[str, Any]:
    """The JSON stored in `groups.split_rule` / `categories.split_rule`."""
    data: dict[str, Any] = spec.model_dump(mode="json", exclude_none=True)
    return data


def spec_from_json(data: dict[str, Any]) -> SplitSpec:
    # Stored JSON has UUIDs as strings: allow that coercion.
    return _SPEC_ADAPTER.validate_python(data, strict=False)
