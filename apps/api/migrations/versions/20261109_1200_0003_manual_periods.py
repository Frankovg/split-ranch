"""Manual periods: no auto-close, periods numbered instead of calendar months.

Members close the open period and start the next one by hand, so a period is no longer
a calendar month: `periods.month`/`closes_at` become `seq`/`started_at`, memberships point
at period numbers, and the household auto-close settings go away.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------------------------------------------- periods
    op.add_column("periods", sa.Column("seq", sa.Integer(), nullable=True), schema="app")
    op.add_column(
        "periods",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    op.execute(
        """
        UPDATE app.periods p
        SET seq = n.seq, started_at = least(p.created_at, p.month::timestamptz)
        FROM (
            SELECT id, row_number() OVER (PARTITION BY household_id ORDER BY month) AS seq
            FROM app.periods
        ) n
        WHERE n.id = p.id
        """
    )
    # Calendar months could leave several periods open at once (grace window); only the
    # latest stays open, so the "one open period" rule holds.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM app.periods p
                WHERE p.status = 'open'
                  AND EXISTS (
                      SELECT 1 FROM app.periods q
                      WHERE q.household_id = p.household_id AND q.status = 'open'
                        AND q.seq > p.seq
                  )
            ) THEN
                RAISE EXCEPTION 'Close all but the latest open period of each household first';
            END IF;
        END $$
        """
    )
    # Every household needs a period to add expenses to.
    op.execute(
        """
        INSERT INTO app.periods (id, household_id, seq, status, started_at, month, closes_at)
        SELECT gen_random_uuid(), h.id, 1, 'open', now(),
               date_trunc('month', now())::date, now()
        FROM app.households h
        WHERE NOT EXISTS (SELECT 1 FROM app.periods p WHERE p.household_id = h.id)
        """
    )

    # ------------------------------------------------------- household_members
    op.add_column(
        "household_members",
        sa.Column("joined_period_seq", sa.Integer(), nullable=True),
        schema="app",
    )
    op.add_column(
        "household_members",
        sa.Column("left_period_seq", sa.Integer(), nullable=True),
        schema="app",
    )
    op.execute(
        """
        UPDATE app.household_members m
        SET joined_period_seq = coalesce(
            (SELECT min(p.seq) FROM app.periods p
             WHERE p.household_id = m.household_id AND p.month >= m.joined_period),
            (SELECT max(p.seq) + 1 FROM app.periods p WHERE p.household_id = m.household_id),
            1
        )
        """
    )
    op.execute(
        """
        UPDATE app.household_members m
        SET left_period_seq = greatest(
            m.joined_period_seq,
            coalesce(
                (SELECT max(p.seq) FROM app.periods p
                 WHERE p.household_id = m.household_id AND p.month <= m.left_period),
                m.joined_period_seq
            )
        )
        WHERE m.left_period IS NOT NULL
        """
    )
    op.alter_column("household_members", "joined_period_seq", nullable=False, schema="app")
    op.drop_constraint(
        op.f("ck_household_members_joined_period_first_day"), "household_members", schema="app"
    )
    op.drop_constraint(
        op.f("ck_household_members_left_period_first_day"), "household_members", schema="app"
    )
    op.drop_column("household_members", "joined_period", schema="app")
    op.drop_column("household_members", "left_period", schema="app")
    op.create_check_constraint(
        op.f("ck_household_members_joined_period_seq_positive"),
        "household_members",
        "joined_period_seq >= 1",
        schema="app",
    )
    op.create_check_constraint(
        op.f("ck_household_members_left_after_joined"),
        "household_members",
        "left_period_seq IS NULL OR left_period_seq >= joined_period_seq",
        schema="app",
    )

    # ------------------------------------------------- periods (drop calendar)
    op.alter_column("periods", "seq", nullable=False, schema="app")
    op.alter_column("periods", "started_at", nullable=False, schema="app")
    op.drop_index("ix_periods_status_closes_at", table_name="periods", schema="app")
    op.drop_constraint(op.f("uq_periods_household_id_month"), "periods", schema="app")
    op.drop_constraint(op.f("ck_periods_month_first_day"), "periods", schema="app")
    op.drop_column("periods", "month", schema="app")
    op.drop_column("periods", "closes_at", schema="app")
    op.create_unique_constraint(
        op.f("uq_periods_household_id_seq"), "periods", ["household_id", "seq"], schema="app"
    )
    op.create_check_constraint(op.f("ck_periods_seq_positive"), "periods", "seq >= 1", schema="app")
    op.create_index(
        "uq_periods_one_open",
        "periods",
        ["household_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("status = 'open'"),
    )

    # -------------------------------------------------------------- households
    op.drop_constraint(op.f("ck_households_grace_days_range"), "households", schema="app")
    op.drop_column("households", "grace_days", schema="app")
    op.drop_column("households", "auto_close", schema="app")


def downgrade() -> None:
    """Map period numbers back onto consecutive months from the household's first period."""
    op.add_column(
        "households",
        sa.Column("auto_close", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        schema="app",
    )
    op.add_column(
        "households",
        sa.Column("grace_days", sa.Integer(), server_default="3", nullable=False),
        schema="app",
    )
    op.create_check_constraint(
        op.f("ck_households_grace_days_range"),
        "households",
        "grace_days BETWEEN 0 AND 15",
        schema="app",
    )

    op.drop_index("uq_periods_one_open", table_name="periods", schema="app")
    op.drop_constraint(op.f("ck_periods_seq_positive"), "periods", schema="app")
    op.drop_constraint(op.f("uq_periods_household_id_seq"), "periods", schema="app")
    op.add_column("periods", sa.Column("month", sa.Date(), nullable=True), schema="app")
    op.add_column(
        "periods",
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    # Base month per household: the month its first period started.
    op.execute(
        """
        CREATE TEMP TABLE period_base ON COMMIT DROP AS
        SELECT h.id AS household_id,
               coalesce(
                   (SELECT date_trunc('month', min(p.started_at))::date
                    FROM app.periods p WHERE p.household_id = h.id),
                   date_trunc('month', now())::date
               ) AS base
        FROM app.households h
        """
    )
    op.execute(
        """
        UPDATE app.periods p
        SET month = (b.base + make_interval(months => p.seq - 1))::date,
            closes_at = b.base + make_interval(months => p.seq, days => 3)
        FROM period_base b
        WHERE b.household_id = p.household_id
        """
    )
    op.alter_column("periods", "month", nullable=False, schema="app")
    op.alter_column("periods", "closes_at", nullable=False, schema="app")
    op.drop_column("periods", "seq", schema="app")
    op.drop_column("periods", "started_at", schema="app")
    op.create_unique_constraint(
        op.f("uq_periods_household_id_month"), "periods", ["household_id", "month"], schema="app"
    )
    op.create_check_constraint(
        op.f("ck_periods_month_first_day"), "periods", "extract(day from month) = 1", schema="app"
    )
    op.create_index("ix_periods_status_closes_at", "periods", ["status", "closes_at"], schema="app")

    op.add_column(
        "household_members", sa.Column("joined_period", sa.Date(), nullable=True), schema="app"
    )
    op.add_column(
        "household_members", sa.Column("left_period", sa.Date(), nullable=True), schema="app"
    )
    op.execute(
        """
        UPDATE app.household_members m
        SET joined_period = (b.base + make_interval(months => m.joined_period_seq - 1))::date,
            left_period = (b.base + make_interval(months => m.left_period_seq - 1))::date
        FROM period_base b
        WHERE b.household_id = m.household_id
        """
    )
    op.alter_column("household_members", "joined_period", nullable=False, schema="app")
    op.drop_constraint(
        op.f("ck_household_members_left_after_joined"), "household_members", schema="app"
    )
    op.drop_constraint(
        op.f("ck_household_members_joined_period_seq_positive"), "household_members", schema="app"
    )
    op.drop_column("household_members", "joined_period_seq", schema="app")
    op.drop_column("household_members", "left_period_seq", schema="app")
    op.create_check_constraint(
        op.f("ck_household_members_joined_period_first_day"),
        "household_members",
        "extract(day from joined_period) = 1",
        schema="app",
    )
    op.create_check_constraint(
        op.f("ck_household_members_left_period_first_day"),
        "household_members",
        "left_period IS NULL OR extract(day from left_period) = 1",
        schema="app",
    )
