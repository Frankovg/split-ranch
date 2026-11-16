"""The authenticated caller passed to every use case. Identity only comes from the JWT."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Actor:
    user_id: UUID


@dataclass(frozen=True)
class GroupActor:
    """An actor with a verified membership in `group_id` (loaded from the DB)."""

    user_id: UUID
    group_id: UUID
    member_id: UUID
    role: str
    status: str

    @property
    def is_admin(self) -> bool:
        """Admin rights end when the member has left: their stored role is kept for history."""
        return self.role == "admin" and self.status != "left"
