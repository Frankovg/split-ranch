"""Drop the 'recurring' value from expenses.split_origin and expenses.source.

Recurring expenses will not be built, so the CHECK constraints no longer allow the value.
No expense can have it (the API never produced it); if one did, the new constraint fails
and the migration rolls back instead of rewriting data.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-26 12:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copies of models.expenses.SPLIT_ORIGINS / EXPENSE_SOURCES at this revision.
SPLIT_ORIGINS = ("override", "category", "group_default")
SOURCES = ("manual", "ai_text", "ai_voice")


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _replace(split_origins: tuple[str, ...], sources: tuple[str, ...]) -> None:
    for name, column, values in (
        ("ck_expenses_split_origin", "split_origin", split_origins),
        ("ck_expenses_source", "source", sources),
    ):
        op.drop_constraint(op.f(name), "expenses", type_="check", schema="app")
        op.create_check_constraint(op.f(name), "expenses", _in(column, values), schema="app")


def upgrade() -> None:
    _replace(SPLIT_ORIGINS, SOURCES)


def downgrade() -> None:
    _replace((*SPLIT_ORIGINS, "recurring"), (*SOURCES, "recurring"))
