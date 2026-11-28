"""Partial index for the live expense list; pin `search_path` on the app functions.

P4: the expense list and every other expense read filter `deleted_at IS NULL` and the list
sorts by (expense_date, created_at, id) DESC, which the old (expense_date, id) index did
not cover. The new partial index matches that order and skips soft-deleted rows. It
replaces the old one: no query reads deleted expenses by group (a single expense is read
by primary key). The tables are small, so a plain CREATE INDEX inside the migration's
transaction is fine (on a large table use CONCURRENTLY in an autocommit block).

B6: the trigger functions run with the caller's `search_path` (Supabase advisor
`function_search_path_mutable`). They already qualify every table with `app.` and only
use pg_catalog built-ins, so an empty `search_path` changes nothing for them and stops
another schema from shadowing a name.

Compatible with the running release: no table or column changes.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-28 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTIONS = (
    "app.assert_expense_shares_sum(uuid)",
    "app.trg_expense_shares_sum()",
    "app.trg_history_append_only()",
)


def upgrade() -> None:
    op.create_index(
        "ix_expenses_group_live_date",
        "expenses",
        ["group_id", sa.text("expense_date DESC"), sa.text("created_at DESC"), sa.text("id DESC")],
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index("ix_expenses_group_date_id", table_name="expenses", schema="app")
    for function in FUNCTIONS:
        op.execute(f"ALTER FUNCTION {function} SET search_path = ''")


def downgrade() -> None:
    for function in FUNCTIONS:
        op.execute(f"ALTER FUNCTION {function} RESET search_path")
    op.create_index(
        "ix_expenses_group_date_id",
        "expenses",
        ["group_id", sa.text("expense_date DESC"), sa.text("id DESC")],
        schema="app",
    )
    op.drop_index("ix_expenses_group_live_date", table_name="expenses", schema="app")
