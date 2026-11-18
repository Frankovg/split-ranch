"""Archive the default "Otros" category: "Other" is now the expense without a category.

New groups no longer get it (DEFAULT_CATEGORIES). Existing groups keep the row, archived,
so expenses that already use it keep their category; each archive is recorded in
`history` like an archive done through the API.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-18 13:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen: the icon key the default "Otros" category was created with.
OTHER_ICON = "dots"
REASON = "Default category replaced by expenses without a category"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
        WITH archived AS (
            UPDATE app.categories
            SET archived_at = now(), updated_at = now()
            WHERE is_default AND icon = :icon AND archived_at IS NULL
            RETURNING id, group_id
        )
        INSERT INTO app.history (id, group_id, entity, entity_id, action, reason, after)
        SELECT gen_random_uuid(), group_id, 'category', id, 'archive', :reason, '{}'::jsonb
        FROM archived
        """
        ).bindparams(icon=OTHER_ICON, reason=REASON)
    )


def downgrade() -> None:
    # History is append-only: the archive rows stay; only the categories come back.
    op.execute(
        sa.text(
            """
        UPDATE app.categories c
        SET archived_at = NULL, updated_at = now()
        WHERE c.is_default AND c.icon = :icon AND c.archived_at IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM app.categories o
              WHERE o.group_id = c.group_id AND o.archived_at IS NULL
                AND lower(o.name) = lower(c.name)
          )
        """
        ).bindparams(icon=OTHER_ICON)
    )
