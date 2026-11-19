"""Push notifications: device tokens and per-user notification preferences.

`push_tokens` holds one Expo push token per device (unique: a phone that switches account
moves its token to the new user). `locale` is the language of the app on that device, used
for the notification text. `last_ticket_id` / `last_ticket_at` keep the latest unchecked
push ticket so its receipt can be read later without a worker.

`users.notification_prefs` stores the in-app switches (everything on by default).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-19 15:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_PREFS = (
    '{"enabled": true, "expense_created": true, "expense_changed": true, '
    '"payments": true, "member_joined": true}'
)

GRANTS_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'split_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON app.push_tokens TO split_api;
    END IF;
END $$;
"""


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notification_prefs",
            postgresql.JSONB(),
            server_default=sa.text(f"'{DEFAULT_PREFS}'::jsonb"),
            nullable=False,
        ),
        schema="app",
    )
    op.create_table(
        "push_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("locale", sa.String(8), server_default="es", nullable=False),
        sa.Column("last_ticket_id", sa.String(64), nullable=True),
        sa.Column("last_ticket_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_tokens")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_push_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token", name=op.f("uq_push_tokens_token")),
        sa.CheckConstraint(
            "token ~ '^Expo(nent)?PushToken\\[.+\\]$'", name=op.f("ck_push_tokens_token_format")
        ),
        sa.CheckConstraint("platform IN ('android', 'ios')", name=op.f("ck_push_tokens_platform")),
        schema="app",
    )
    op.create_index(
        op.f("ix_push_tokens_user_id"), "push_tokens", ["user_id"], unique=False, schema="app"
    )
    # Defence in depth, like every app table: RLS enabled with no policies.
    op.execute("ALTER TABLE app.push_tokens ENABLE ROW LEVEL SECURITY")
    op.execute(GRANTS_SQL)


def downgrade() -> None:
    op.drop_table("push_tokens", schema="app")
    op.drop_column("users", "notification_prefs", schema="app")
