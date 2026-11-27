"""The authenticated caller passed to every use case. Identity only comes from the JWT."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Actor:
    user_id: UUID


@dataclass(frozen=True)
class GroupActor:
    """An actor who is an active member of `group_id` (loaded from the DB).

    Only `api.deps.get_group_actor` builds one, and it answers 404 to outsiders and to
    members who left. Use cases rely on that: they do not check the membership again.
    """

    user_id: UUID
    group_id: UUID
    member_id: UUID
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
