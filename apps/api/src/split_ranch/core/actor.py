"""The authenticated caller passed to every use case. Identity only comes from the JWT."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Actor:
    user_id: UUID


@dataclass(frozen=True)
class HouseholdActor:
    """An actor with a verified membership in `household_id` (loaded from the DB)."""

    user_id: UUID
    household_id: UUID
    member_id: UUID
    role: str
    status: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
