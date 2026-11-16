"""Baseline schema: users, households with manual periods, expenses, settlement transfers.

This is the first migration. It replaces the older chain (initial schema, job queue, manual
periods, drop Quick splits, simplify), which was squashed because the database holds no
data worth keeping (decision D3, docs/egm/design_draft.md). The tables are built from
frozen definitions below, so constraint and index names follow the naming convention.

Revision ID: 0005
Revises:
Create Date: 2026-11-11 12:00:00+00:00
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SPLIT_TYPES = ("equal", "weights", "percentages", "exact", "single", "personal")
DEFAULT_RULE = sa.text("""'{"split_type": "equal"}'::jsonb""")

# Every table of this revision except `users`, which is created by hand in `upgrade()`.
TABLES = (
    "households",
    "household_members",
    "categories",
    "periods",
    "expenses",
    "expense_shares",
    "settlement_transfers",
    "history",
)

FUNCTIONS_SQL = """
CREATE FUNCTION app.assert_expense_shares_sum(p_expense_id uuid) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    v_amount bigint;
    v_sum bigint;
    v_wrong_sign int;
BEGIN
    SELECT amount_cents INTO v_amount FROM app.expenses WHERE id = p_expense_id;
    IF NOT FOUND THEN
        RETURN;  -- expense removed in the same transaction
    END IF;
    SELECT coalesce(sum(amount_cents), 0),
           count(*) FILTER (WHERE sign(amount_cents) = -sign(v_amount))
      INTO v_sum, v_wrong_sign
      FROM app.expense_shares WHERE expense_id = p_expense_id;
    IF v_sum <> v_amount THEN
        RAISE EXCEPTION 'expense % shares sum % does not match amount %', p_expense_id, v_sum, v_amount
            USING ERRCODE = 'check_violation', CONSTRAINT = 'expense_shares_sum';
    END IF;
    IF v_wrong_sign > 0 THEN
        RAISE EXCEPTION 'expense % has shares with the opposite sign of its amount', p_expense_id
            USING ERRCODE = 'check_violation', CONSTRAINT = 'expense_shares_sign';
    END IF;
END $$;

CREATE FUNCTION app.trg_expense_shares_sum() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'expenses' THEN
        PERFORM app.assert_expense_shares_sum(NEW.id);
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM app.assert_expense_shares_sum(OLD.expense_id);
    ELSE
        PERFORM app.assert_expense_shares_sum(NEW.expense_id);
        IF TG_OP = 'UPDATE' AND OLD.expense_id <> NEW.expense_id THEN
            PERFORM app.assert_expense_shares_sum(OLD.expense_id);
        END IF;
    END IF;
    RETURN NULL;
END $$;

CREATE FUNCTION app.trg_history_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'history is append-only' USING ERRCODE = 'insufficient_privilege';
END $$;
"""

TRIGGERS_SQL = """
CREATE CONSTRAINT TRIGGER expense_shares_sum
    AFTER INSERT OR UPDATE OR DELETE ON app.expense_shares
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION app.trg_expense_shares_sum();

CREATE CONSTRAINT TRIGGER expenses_shares_sum
    AFTER INSERT OR UPDATE OF amount_cents ON app.expenses
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION app.trg_expense_shares_sum();

CREATE TRIGGER history_append_only
    BEFORE UPDATE ON app.history
    FOR EACH ROW EXECUTE FUNCTION app.trg_history_append_only();
"""

# The runtime role is created by infra (it needs a password); grant only if it exists.
GRANTS_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'split_api') THEN
        GRANT USAGE ON SCHEMA app TO split_api;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO split_api;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO split_api;
        GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO split_api;
        REVOKE UPDATE, DELETE ON app.history FROM split_api;
    END IF;
END $$;
"""


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _metadata() -> sa.MetaData:
    md = sa.MetaData(schema="app", naming_convention=NAMING_CONVENTION)
    # Only referenced by foreign keys; never created or dropped here.
    sa.Table("users", md, sa.Column("id", sa.Uuid(), primary_key=True))
    return md


def _ts(name: str, *, nullable: bool = False, server_now: bool = False) -> sa.Column[Any]:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=sa.func.now() if server_now else None,
    )


def _common_group(md: sa.MetaData, t: str, m: str, *, old: bool) -> None:
    """`groups`/`households`, members and categories (same shape in both revisions)."""
    k = "household_id" if old else "group_id"
    sa.Table(
        t,
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/Madrid"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("split_rule", JSONB(), nullable=False, server_default=DEFAULT_RULE),
        sa.Column("invite_code", sa.String(8), nullable=True, unique=True),
        _ts("invite_expires_at", nullable=True),
        _ts("created_at", server_now=True),
        _ts("updated_at", server_now=True),
        _ts("deleted_at", nullable=True),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 80", name="name_length"),
        sa.CheckConstraint(
            "invite_code IS NULL OR char_length(invite_code) = 8", name="invite_code_length"
        ),
    )
    if old:
        member_cols: list[Any] = [
            sa.Column("joined_period_seq", sa.Integer(), nullable=False),
            sa.Column("left_period_seq", sa.Integer(), nullable=True),
            sa.CheckConstraint(_in("status", ("active", "leaving", "left")), name="status"),
            sa.CheckConstraint("joined_period_seq >= 1", name="joined_period_seq_positive"),
            sa.CheckConstraint(
                "left_period_seq IS NULL OR left_period_seq >= joined_period_seq",
                name="left_after_joined",
            ),
        ]
    else:
        member_cols = [
            _ts("joined_at"),
            _ts("left_at", nullable=True),
            sa.CheckConstraint(_in("status", ("active", "left")), name="status"),
            sa.CheckConstraint("left_at IS NULL OR left_at >= joined_at", name="left_after_joined"),
        ]
    members = sa.Table(
        m,
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(k, sa.Uuid(), sa.ForeignKey(f"{t}.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("sort_key", sa.Integer(), nullable=False, server_default="0"),
        *member_cols,
        _ts("created_at", server_now=True),
        _ts("updated_at", server_now=True),
        sa.UniqueConstraint(k, "user_id"),
        sa.UniqueConstraint("id", k),
        sa.CheckConstraint(_in("role", ("admin", "member")), name="role"),
    )
    sa.Index(f"ix_{m}_active", members.c[k], postgresql_where=sa.text("status <> 'left'"))
    if not old:
        sa.Index(
            "uq_group_members_one_admin",
            members.c[k],
            unique=True,
            postgresql_where=sa.text("role = 'admin' AND status = 'active'"),
        )
    categories = sa.Table(
        "categories",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(k, sa.Uuid(), sa.ForeignKey(f"{t}.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("icon", sa.String(40), nullable=True),
        sa.Column("color", sa.String(16), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _ts("archived_at", nullable=True),
        sa.Column("sort_key", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("split_rule", JSONB(), nullable=True),
        _ts("created_at", server_now=True),
        _ts("updated_at", server_now=True),
        sa.UniqueConstraint("id", k),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 40", name="name_length"),
    )
    sa.Index(
        f"uq_categories_{t[:-1] if not old else 'household'}_name",
        categories.c[k],
        sa.func.lower(sa.text("name")),
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def _expense_cols(k: str) -> list[Any]:
    return [
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("payer_member_id", sa.Uuid(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.String(140), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("split_type", sa.String(16), nullable=False),
        sa.Column("split_origin", sa.String(24), nullable=False),
        sa.Column("participant_mode", sa.String(8), nullable=False, server_default="all"),
        sa.Column("rule_fallback", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
    ]


def _expense_tail() -> list[Any]:
    return [
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        _ts("created_at", server_now=True),
        _ts("updated_at", server_now=True),
        _ts("deleted_at", nullable=True),
        sa.Column("deleted_reason", sa.String(280), nullable=True),
        sa.CheckConstraint("char_length(description) BETWEEN 1 AND 140", name="description_length"),
        sa.CheckConstraint(_in("split_type", SPLIT_TYPES), name="split_type"),
        sa.CheckConstraint(_in("participant_mode", ("all", "subset")), name="participant_mode"),
    ]


def _shares(md: sa.MetaData, k: str, members: str) -> None:
    shares = sa.Table(
        "expense_shares",
        md,
        sa.Column("expense_id", sa.Uuid(), primary_key=True),
        sa.Column("member_id", sa.Uuid(), primary_key=True),
        sa.Column(k, sa.Uuid(), nullable=False),
        sa.Column("sort_key", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=True),
        sa.Column("basis_points", sa.Integer(), nullable=True),
        sa.Column("exact_cents", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["expense_id", k], ["expenses.id", f"expenses.{k}"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["member_id", k], [f"{members}.id", f"{members}.{k}"]),
    )
    sa.Index("ix_expense_shares_member", shares.c[k], shares.c.member_id)


def _history(md: sa.MetaData, k: str, t: str) -> None:
    history = sa.Table(
        "history",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            k, sa.Uuid(), sa.ForeignKey(f"{t}.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column("entity", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reason", sa.String(280), nullable=True),
        sa.Column("before", JSONB(), nullable=True),
        sa.Column("after", JSONB(), nullable=True),
        _ts("created_at", server_now=True),
    )
    sa.Index("ix_history_entity", history.c.entity, history.c.entity_id, history.c.created_at)
    sa.Index(
        "uq_history_expense_version",
        history.c.entity_id,
        history.c.version,
        unique=True,
        postgresql_where=sa.text("entity = 'expense'"),
    )


def _schema() -> sa.MetaData:
    """The tables of this revision (households, periods and settlement transfers)."""
    md = _metadata()
    k = "household_id"
    _common_group(md, "households", "household_members", old=True)
    periods = sa.Table(
        "periods",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(k, sa.Uuid(), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        _ts("started_at"),
        _ts("closed_at", nullable=True),
        sa.Column("closed_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        _ts("settled_at", nullable=True),
        sa.Column("reopened_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        _ts("created_at", server_now=True),
        _ts("updated_at", server_now=True),
        sa.UniqueConstraint(k, "seq"),
        sa.UniqueConstraint("id", k),
        sa.CheckConstraint(_in("status", ("open", "closed", "settled")), name="status"),
        sa.CheckConstraint("seq >= 1", name="seq_positive"),
    )
    sa.Index(
        "uq_periods_one_open",
        periods.c[k],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    expenses = sa.Table(
        "expenses",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(k, sa.Uuid(), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        *_expense_cols(k),
        sa.Column("adjusts_expense_id", sa.Uuid(), nullable=True),
        *_expense_tail(),
        sa.UniqueConstraint("id", k),
        sa.ForeignKeyConstraint(["period_id", k], ["periods.id", "periods.household_id"]),
        sa.ForeignKeyConstraint(
            ["payer_member_id", k], ["household_members.id", "household_members.household_id"]
        ),
        sa.ForeignKeyConstraint(["category_id", k], ["categories.id", "categories.household_id"]),
        sa.ForeignKeyConstraint(
            ["adjusts_expense_id", k], ["expenses.id", "expenses.household_id"]
        ),
        sa.CheckConstraint(
            "amount_cents <> 0 AND (amount_cents > 0 OR source = 'adjustment')"
            " AND abs(amount_cents) <= 100000000",
            name="amount",
        ),
        sa.CheckConstraint(
            _in("split_origin", ("override", "category", "recurring", "household_default")),
            name="split_origin",
        ),
        sa.CheckConstraint(
            _in("source", ("manual", "ai_text", "ai_voice", "recurring", "adjustment")),
            name="source",
        ),
        sa.CheckConstraint(
            "source <> 'adjustment' OR adjusts_expense_id IS NOT NULL", name="adjustment_link"
        ),
    )
    sa.Index(
        "ix_expenses_household_period_live",
        expenses.c[k],
        expenses.c.period_id,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    sa.Index(
        "ix_expenses_household_date_id",
        expenses.c[k],
        sa.text("expense_date DESC"),
        sa.text("id DESC"),
    )
    _shares(md, k, "household_members")
    sa.Table(
        "settlement_transfers",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(k, sa.Uuid(), nullable=False, index=True),
        sa.Column("period_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("from_member_id", sa.Uuid(), nullable=False),
        sa.Column("to_member_id", sa.Uuid(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        _ts("sent_at", nullable=True),
        _ts("confirmed_at", nullable=True),
        sa.Column("confirmed_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.String(280), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        _ts("created_at", server_now=True),
        _ts("updated_at", server_now=True),
        sa.ForeignKeyConstraint(
            ["period_id", k], ["periods.id", "periods.household_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["from_member_id", k], ["household_members.id", "household_members.household_id"]
        ),
        sa.ForeignKeyConstraint(
            ["to_member_id", k], ["household_members.id", "household_members.household_id"]
        ),
        sa.CheckConstraint("amount_cents > 0", name="amount_positive"),
        sa.CheckConstraint("from_member_id <> to_member_id", name="distinct_members"),
        sa.CheckConstraint(
            _in("status", ("pending", "sent", "confirmed", "disputed", "cancelled")),
            name="status",
        ),
    )
    _history(md, k, "households")
    return md


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("locale", sa.String(length=16), server_default="es-ES", nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        schema="app",
    )
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.literal_column("lower(email)")],
        unique=True,
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL AND email IS NOT NULL"),
    )

    md = _schema()
    md.create_all(op.get_bind(), tables=[md.tables[f"app.{t}"] for t in TABLES])
    op.execute(FUNCTIONS_SQL)
    op.execute(TRIGGERS_SQL)
    # Defence in depth: RLS enabled with no policies, so anon/authenticated read nothing.
    for table in ("users", *TABLES):
        op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(GRANTS_SQL)


def downgrade() -> None:
    for trigger, table in (
        ("expense_shares_sum", "expense_shares"),
        ("expenses_shares_sum", "expenses"),
        ("history_append_only", "history"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON app.{table}")
    for function in (
        "trg_expense_shares_sum()",
        "assert_expense_shares_sum(uuid)",
        "trg_history_append_only()",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS app.{function}")
    md = _schema()
    md.drop_all(op.get_bind(), tables=[md.tables[f"app.{t}"] for t in TABLES])
    op.drop_index(
        "uq_users_email_lower",
        table_name="users",
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL AND email IS NOT NULL"),
    )
    op.drop_table("users", schema="app")
