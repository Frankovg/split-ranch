"""New default category list for existing groups.

The defaults are now: Entertainment, Groceries, Healthcare, Home, Insurance, Rent and
Services, Restaurants and bars, Shopping and Transport ("Other" = no category). Existing
groups lose the utility defaults (electricity, water, gas, internet: now part of "Rent
and Services") and get Insurance and Shopping. The app names default categories by icon
key, so the kept rows need no rename. Archived rows stay, so expenses that use them keep
their category; every change is recorded in `history` like the API does.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-18 14:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copies at this revision: (name, icon key, color).
REMOVED_ICONS = ("bolt", "droplet", "flame", "wifi")
ADDED = (("Insurance", "shield", "#607D8B"), ("Shopping", "bag", "#FF9800"))
REASON = "Default category list changed"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
        WITH archived AS (
            UPDATE app.categories
            SET archived_at = now(), updated_at = now()
            WHERE is_default AND icon = ANY(:icons) AND archived_at IS NULL
            RETURNING id, group_id
        )
        INSERT INTO app.history (id, group_id, entity, entity_id, action, reason, after)
        SELECT gen_random_uuid(), group_id, 'category', id, 'archive', :reason, '{}'::jsonb
        FROM archived
        """
        ).bindparams(icons=list(REMOVED_ICONS), reason=REASON)
    )
    for name, icon, color in ADDED:
        # Skip groups that already have it, or an active category with the same name.
        op.execute(
            sa.text(
                """
            WITH created AS (
                INSERT INTO app.categories (id, group_id, name, icon, color, is_default, sort_key)
                SELECT gen_random_uuid(), g.id, :name, :icon, :color, true,
                       COALESCE((SELECT max(c.sort_key) FROM app.categories c
                                 WHERE c.group_id = g.id), -1) + 1
                FROM app.groups g
                WHERE g.deleted_at IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM app.categories c
                      WHERE c.group_id = g.id AND c.archived_at IS NULL
                        AND (lower(c.name) = lower(:name) OR (c.is_default AND c.icon = :icon))
                  )
                RETURNING id, group_id
            )
            INSERT INTO app.history (id, group_id, entity, entity_id, action, reason, after)
            SELECT gen_random_uuid(), group_id, 'category', id, 'create', :reason,
                   jsonb_build_object('name', CAST(:name AS text))
            FROM created
            """
            ).bindparams(name=name, icon=icon, color=color, reason=REASON)
        )


def downgrade() -> None:
    # History is append-only: its rows stay. Added defaults go unless an expense uses them.
    op.execute(
        sa.text(
            """
        DELETE FROM app.categories c
        WHERE c.is_default AND c.icon = ANY(:icons)
          AND NOT EXISTS (SELECT 1 FROM app.expenses e WHERE e.category_id = c.id)
        """
        ).bindparams(icons=[icon for _, icon, _ in ADDED])
    )
    op.execute(
        sa.text(
            """
        UPDATE app.categories c
        SET archived_at = NULL, updated_at = now()
        WHERE c.is_default AND c.icon = ANY(:icons) AND c.archived_at IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM app.categories o
              WHERE o.group_id = c.group_id AND o.archived_at IS NULL
                AND lower(o.name) = lower(c.name)
          )
        """
        ).bindparams(icons=list(REMOVED_ICONS))
    )
