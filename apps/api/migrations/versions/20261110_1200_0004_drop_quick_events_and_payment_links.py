"""Drop server-side Quick splits and every link to payment platforms.

Quick splits now live only on the user's phone: they are never saved, synced or shared
through the API, so the `quick_*` tables, their share-sum triggers and functions go away.
The app does not link to payment platforms either, so `users.payment_handles` (Bizum
phone, PayPal.me, Revolut) and `settlement_transfers.method` are dropped as well.
The downgrade recreates everything as migration 0001 created it (data is not restored).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QUICK_TABLES = ("quick_events", "quick_participants", "quick_expenses", "quick_expense_shares")

QUICK_SHARE_SUM_SQL = """
CREATE FUNCTION app.assert_quick_expense_shares_sum(p_expense_id uuid) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    v_amount bigint;
    v_sum bigint;
BEGIN
    SELECT amount_cents INTO v_amount FROM app.quick_expenses WHERE id = p_expense_id;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    SELECT coalesce(sum(amount_cents), 0) INTO v_sum
      FROM app.quick_expense_shares WHERE quick_expense_id = p_expense_id;
    IF v_sum <> v_amount THEN
        RAISE EXCEPTION 'quick expense % shares sum % does not match amount %', p_expense_id, v_sum, v_amount
            USING ERRCODE = 'check_violation', CONSTRAINT = 'quick_expense_shares_sum';
    END IF;
END $$;

CREATE FUNCTION app.trg_quick_expense_shares_sum() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'quick_expenses' THEN
        PERFORM app.assert_quick_expense_shares_sum(NEW.id);
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM app.assert_quick_expense_shares_sum(OLD.quick_expense_id);
    ELSE
        PERFORM app.assert_quick_expense_shares_sum(NEW.quick_expense_id);
    END IF;
    RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER quick_expense_shares_sum
    AFTER INSERT OR UPDATE OR DELETE ON app.quick_expense_shares
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION app.trg_quick_expense_shares_sum();

CREATE CONSTRAINT TRIGGER quick_expenses_shares_sum
    AFTER INSERT OR UPDATE OF amount_cents ON app.quick_expenses
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION app.trg_quick_expense_shares_sum();
"""

QUICK_GRANTS_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'split_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            app.quick_events, app.quick_participants, app.quick_expenses, app.quick_expense_shares
            TO split_api;
        GRANT EXECUTE ON FUNCTION app.assert_quick_expense_shares_sum(uuid),
            app.trg_quick_expense_shares_sum() TO split_api;
    END IF;
END $$;
"""


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS quick_expense_shares_sum ON app.quick_expense_shares")
    op.execute("DROP TRIGGER IF EXISTS quick_expenses_shares_sum ON app.quick_expenses")
    op.execute("DROP FUNCTION IF EXISTS app.trg_quick_expense_shares_sum()")
    op.execute("DROP FUNCTION IF EXISTS app.assert_quick_expense_shares_sum(uuid)")
    op.drop_table("quick_expense_shares", schema="app")
    op.drop_index(op.f("ix_quick_expenses_event_id"), table_name="quick_expenses", schema="app")
    op.drop_table("quick_expenses", schema="app")
    op.drop_index("uq_quick_participants_event_name", table_name="quick_participants", schema="app")
    op.drop_table("quick_participants", schema="app")
    op.drop_index(
        "ix_quick_events_owner_live",
        table_name="quick_events",
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("quick_events", schema="app")

    # ------------------------------------------------------ payment links
    op.drop_column("users", "payment_handles", schema="app")
    op.drop_constraint(
        op.f("ck_settlement_transfers_method"), "settlement_transfers", schema="app", type_="check"
    )
    op.drop_column("settlement_transfers", "method", schema="app")


def downgrade() -> None:
    """Recreate the dropped columns and the empty Quick split tables as in 0001."""
    op.add_column(
        "settlement_transfers",
        sa.Column("method", sa.String(length=16), nullable=True),
        schema="app",
    )
    op.create_check_constraint(
        op.f("ck_settlement_transfers_method"),
        "settlement_transfers",
        "method IS NULL OR method IN ('bizum', 'paypal', 'cash', 'other')",
        schema="app",
    )
    op.add_column(
        "users",
        sa.Column(
            "payment_handles",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        schema="app",
    )
    op.create_table(
        "quick_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
        sa.Column("share_token", sa.String(length=32), nullable=True),
        sa.Column("share_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("currency = 'EUR'", name=op.f("ck_quick_events_currency_eur")),
        sa.CheckConstraint("mode IN ('total', 'itemised')", name=op.f("ck_quick_events_mode")),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 80", name=op.f("ck_quick_events_title_length")
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["app.users.id"],
            name=op.f("fk_quick_events_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quick_events")),
        sa.UniqueConstraint("share_token", name=op.f("uq_quick_events_share_token")),
        schema="app",
    )
    op.create_index(
        "ix_quick_events_owner_live",
        "quick_events",
        ["owner_user_id", sa.literal_column("updated_at DESC")],
        unique=False,
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "quick_participants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("sort_key", sa.Integer(), server_default="0", nullable=False),
        sa.Column("weight", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 40", name=op.f("ck_quick_participants_name_length")
        ),
        sa.CheckConstraint("weight >= 0", name=op.f("ck_quick_participants_weight_non_negative")),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["app.quick_events.id"],
            name=op.f("fk_quick_participants_event_id_quick_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_quick_participants_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quick_participants")),
        sa.UniqueConstraint("id", "event_id", name=op.f("uq_quick_participants_id_event_id")),
        schema="app",
    )
    op.create_index(
        "uq_quick_participants_event_name",
        "quick_participants",
        ["event_id", sa.literal_column("lower(name)")],
        unique=True,
        schema="app",
    )
    op.create_table(
        "quick_expenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("payer_participant_id", sa.Uuid(), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.String(length=140), nullable=True),
        sa.Column("split_type", sa.String(length=16), nullable=False),
        sa.Column("sort_key", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "split_type IN ('equal', 'weights', 'exact')", name=op.f("ck_quick_expenses_split_type")
        ),
        sa.CheckConstraint(
            "amount_cents > 0 AND amount_cents <= 100000000", name=op.f("ck_quick_expenses_amount")
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["app.quick_events.id"],
            name=op.f("fk_quick_expenses_event_id_quick_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["payer_participant_id", "event_id"],
            ["app.quick_participants.id", "app.quick_participants.event_id"],
            name=op.f("fk_quick_expenses_payer_participant_id_event_id_quick_participants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quick_expenses")),
        sa.UniqueConstraint("id", "event_id", name=op.f("uq_quick_expenses_id_event_id")),
        schema="app",
    )
    op.create_index(
        op.f("ix_quick_expenses_event_id"),
        "quick_expenses",
        ["event_id"],
        unique=False,
        schema="app",
    )
    op.create_table(
        "quick_expense_shares",
        sa.Column("quick_expense_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=True),
        sa.Column("exact_cents", sa.BigInteger(), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "amount_cents >= 0", name=op.f("ck_quick_expense_shares_amount_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["participant_id", "event_id"],
            ["app.quick_participants.id", "app.quick_participants.event_id"],
            name=op.f("fk_quick_expense_shares_participant_id_event_id_quick_participants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["quick_expense_id", "event_id"],
            ["app.quick_expenses.id", "app.quick_expenses.event_id"],
            name=op.f("fk_quick_expense_shares_quick_expense_id_event_id_quick_expenses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "quick_expense_id", "participant_id", name=op.f("pk_quick_expense_shares")
        ),
        schema="app",
    )
    op.execute(QUICK_SHARE_SUM_SQL)
    for table in QUICK_TABLES:
        op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(QUICK_GRANTS_SQL)
