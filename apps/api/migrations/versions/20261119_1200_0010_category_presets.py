"""Category presets: keywords that pick a category for new expenses.

Each group keeps its own list (empty by default). The app matches the keywords against
the description while an expense is typed; the API only stores them. A preset goes with
its category (composite tenant-safe FK) and with its group.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-19 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'split_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON app.category_presets TO split_api;
    END IF;
END $$;
"""


def upgrade() -> None:
    op.create_table(
        "category_presets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("keyword", sa.String(40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_category_presets")),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["app.groups.id"],
            name=op.f("fk_category_presets_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id", "group_id"],
            ["app.categories.id", "app.categories.group_id"],
            name=op.f("fk_category_presets_category_id_group_id_categories"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "char_length(keyword) BETWEEN 1 AND 40",
            name=op.f("ck_category_presets_keyword_length"),
        ),
        schema="app",
    )
    op.create_index(
        "uq_category_presets_group_keyword",
        "category_presets",
        ["group_id", sa.text("lower(keyword)")],
        unique=True,
        schema="app",
    )
    # Defence in depth, like every app table: RLS enabled with no policies.
    op.execute("ALTER TABLE app.category_presets ENABLE ROW LEVEL SECURITY")
    op.execute(GRANTS_SQL)


def downgrade() -> None:
    op.drop_table("category_presets", schema="app")
