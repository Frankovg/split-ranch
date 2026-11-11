"""Simplify the schema: 18 app tables (+4 Procrastinate) down to 9.

- Split rules live as JSON (`households.split_rule`, `categories.split_rule`) instead of
  `split_rules` + `split_rule_shares`. The JSON is the API's `SplitSpec`.
- One `history` table replaces `expense_revisions` and `audit_log`.
- Settlement transfers belong to their period only: `settlement_snapshots` goes away
  (balances are always recomputed from the expenses; superseded transfers stay as
  `cancelled`).
- One invitation code per household (`households.invite_code`) replaces `invitations`.
- `idempotency_keys` goes away: the client-generated expense id already makes creating an
  expense idempotent.
- Unbuilt features lose their tables: Google Sheets (`household_spreadsheets`,
  `sheet_tabs`), push notifications (`push_tokens`) and the Procrastinate job queue.
- Dead columns go: `currency` (always EUR), `households.version`,
  `household_members.display_name_override`, `expenses.status` (drafts),
  `expenses.source_transcript`, `expenses.recurring_expense_id`.

Data is migrated forwards (rules, history, the newest usable invitation). Draft expenses,
which never counted in any balance, are deleted. The downgrade recreates the old structure
and moves rules, history and the invite code back; push tokens, idempotency keys, Sheets
bookkeeping and settlement snapshots come back empty or approximated (one snapshot per
period that has transfers).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11 12:00:00+00:00
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROCRASTINATE_SCHEMA_FILE = (
    Path(__file__).resolve().parents[1] / "sql" / "procrastinate_3.10.0_schema.sql"
)

DEFAULT_RULE_SQL = """'{"split_type": "equal"}'::jsonb"""

# Same statement as migration 0002's downgrade: removes every Procrastinate object in `app`.
DROP_PROCRASTINATE_SQL = """
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT tgname, c.relname FROM pg_trigger t
             JOIN pg_class c ON c.oid = t.tgrelid
             JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'app' AND c.relname LIKE 'procrastinate%' AND NOT t.tgisinternal
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON app.%I', r.tgname, r.relname);
    END LOOP;
    FOR r IN SELECT p.oid::regprocedure AS sig FROM pg_proc p
             JOIN pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'app' AND p.proname LIKE 'procrastinate%'
    LOOP
        EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END LOOP;
    FOR r IN SELECT c.relname FROM pg_class c
             JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'app' AND c.relkind = 'r' AND c.relname LIKE 'procrastinate%'
    LOOP
        EXECUTE format('DROP TABLE IF EXISTS app.%I CASCADE', r.relname);
    END LOOP;
    FOR r IN SELECT t.typname FROM pg_type t
             JOIN pg_namespace n ON n.oid = t.typnamespace
             WHERE n.nspname = 'app' AND t.typname LIKE 'procrastinate%' AND t.typtype IN ('e', 'c')
               AND NOT EXISTS (SELECT 1 FROM pg_class c WHERE c.reltype = t.oid AND c.relkind = 'r')
    LOOP
        EXECUTE format('DROP TYPE IF EXISTS app.%I CASCADE', r.typname);
    END LOOP;
END $$;
"""

HISTORY_APPEND_ONLY_SQL = """
CREATE FUNCTION app.trg_history_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'history is append-only' USING ERRCODE = 'insufficient_privilege';
END $$;

CREATE TRIGGER history_append_only
    BEFORE UPDATE ON app.history
    FOR EACH ROW EXECUTE FUNCTION app.trg_history_append_only();
"""

OLD_APPEND_ONLY_SQL = """
CREATE FUNCTION app.trg_expense_revisions_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'expense_revisions is append-only' USING ERRCODE = 'insufficient_privilege';
END $$;

CREATE TRIGGER expense_revisions_append_only
    BEFORE UPDATE ON app.expense_revisions
    FOR EACH ROW EXECUTE FUNCTION app.trg_expense_revisions_append_only();

CREATE FUNCTION app.trg_settlement_snapshots_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (to_jsonb(NEW) - 'superseded_at') <> (to_jsonb(OLD) - 'superseded_at') THEN
        RAISE EXCEPTION 'settlement_snapshots are immutable except superseded_at'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER settlement_snapshots_immutable
    BEFORE UPDATE ON app.settlement_snapshots
    FOR EACH ROW EXECUTE FUNCTION app.trg_settlement_snapshots_immutable();
"""

GRANTS_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'split_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO split_api;
        GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO split_api;
        {extra}
    END IF;
END $$;
"""

OLD_TABLES = (
    "split_rules",
    "split_rule_shares",
    "expense_revisions",
    "audit_log",
    "settlement_snapshots",
    "invitations",
    "idempotency_keys",
    "push_tokens",
    "household_spreadsheets",
    "sheet_tabs",
)


# =============================================================================== upgrade


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS expense_revisions_append_only ON app.expense_revisions")
    op.execute("DROP FUNCTION IF EXISTS app.trg_expense_revisions_append_only()")
    op.execute("DROP TRIGGER IF EXISTS settlement_snapshots_immutable ON app.settlement_snapshots")
    op.execute("DROP FUNCTION IF EXISTS app.trg_settlement_snapshots_immutable()")

    _add_new_columns()
    _create_history()
    _migrate_data_forwards()

    for table in (
        "split_rule_shares",
        "split_rules",
        "expense_revisions",
        "audit_log",
        "invitations",
        "idempotency_keys",
        "push_tokens",
        "sheet_tabs",
        "household_spreadsheets",
    ):
        op.drop_table(table, schema="app")
    op.drop_constraint(
        op.f("fk_settlement_transfers_snapshot_id_household_id_settlement_snapshots"),
        "settlement_transfers",
        schema="app",
        type_="foreignkey",
    )
    op.drop_column("settlement_transfers", "snapshot_id", schema="app")
    op.drop_table("settlement_snapshots", schema="app")

    _drop_dead_columns()

    op.execute(HISTORY_APPEND_ONLY_SQL)
    op.execute("ALTER TABLE app.history ENABLE ROW LEVEL SECURITY")
    op.execute(GRANTS_SQL.format(extra="REVOKE UPDATE, DELETE ON app.history FROM split_api;"))
    op.execute(DROP_PROCRASTINATE_SQL)


def _add_new_columns() -> None:
    op.add_column(
        "households", sa.Column("invite_code", sa.String(length=8), nullable=True), schema="app"
    )
    op.add_column(
        "households",
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    op.add_column(
        "households",
        sa.Column(
            "split_rule",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(DEFAULT_RULE_SQL),
            nullable=False,
        ),
        schema="app",
    )
    op.create_unique_constraint(
        op.f("uq_households_invite_code"), "households", ["invite_code"], schema="app"
    )
    op.create_check_constraint(
        op.f("ck_households_invite_code_length"),
        "households",
        "invite_code IS NULL OR char_length(invite_code) = 8",
        schema="app",
    )
    op.add_column(
        "categories",
        sa.Column("split_rule", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="app",
    )


def _create_history() -> None:
    op.create_table(
        "history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("entity", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=280), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["app.users.id"], name=op.f("fk_history_actor_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["app.households.id"],
            name=op.f("fk_history_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_history")),
        schema="app",
    )
    op.create_index(
        "ix_history_entity", "history", ["entity", "entity_id", "created_at"], schema="app"
    )
    op.create_index(op.f("ix_history_household_id"), "history", ["household_id"], schema="app")
    op.create_index(
        "uq_history_expense_version",
        "history",
        ["entity_id", "version"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("entity = 'expense'"),
    )


def _migrate_data_forwards() -> None:
    # Drafts never entered a balance; their revisions go with them (ON DELETE CASCADE).
    op.execute("DELETE FROM app.expenses WHERE status = 'draft'")

    op.execute(
        """
        INSERT INTO app.history
            (id, household_id, entity, entity_id, version, action, actor_user_id, reason,
             before, after, created_at)
        SELECT id, household_id, 'expense', expense_id, version, action, actor_user_id,
               reason, before, after, created_at
        FROM app.expense_revisions
        """
    )
    op.execute(
        """
        INSERT INTO app.history
            (id, household_id, entity, entity_id, action, actor_user_id, after, created_at)
        SELECT id, household_id, entity, entity_id, action, actor_user_id, diff, created_at
        FROM app.audit_log
        WHERE household_id IS NOT NULL
        """
    )

    # Rules become the JSON the API accepts (`SplitSpec`), shares in their stored order.
    op.execute(
        """
        CREATE TEMP TABLE rule_json ON COMMIT DROP AS
        SELECT r.household_id, r.scope, r.category_id,
               CASE
                   WHEN r.split_type = 'personal' THEN jsonb_build_object('split_type', 'personal')
                   WHEN NOT EXISTS (
                       SELECT 1 FROM app.split_rule_shares s WHERE s.split_rule_id = r.id
                   ) THEN jsonb_build_object('split_type', r.split_type)
                   ELSE jsonb_build_object(
                       'split_type', r.split_type,
                       'shares', (
                           SELECT jsonb_agg(
                               CASE r.split_type
                                   WHEN 'weights' THEN jsonb_build_object(
                                       'member_id', s.member_id, 'weight', s.weight)
                                   WHEN 'percentages' THEN jsonb_build_object(
                                       'member_id', s.member_id, 'basis_points', s.basis_points)
                                   WHEN 'exact' THEN jsonb_build_object(
                                       'member_id', s.member_id, 'amount_cents', s.amount_cents)
                                   ELSE jsonb_build_object('member_id', s.member_id)
                               END
                               ORDER BY s.sort_key, s.member_id)
                           FROM app.split_rule_shares s
                           WHERE s.split_rule_id = r.id
                       )
                   )
               END AS spec
        FROM app.split_rules r
        WHERE r.scope IN ('household_default', 'category')
        """
    )
    op.execute(
        """
        UPDATE app.households h SET split_rule = j.spec
        FROM rule_json j
        WHERE j.scope = 'household_default' AND j.household_id = h.id
        """
    )
    op.execute(
        """
        UPDATE app.categories c SET split_rule = j.spec
        FROM rule_json j
        WHERE j.scope = 'category' AND j.category_id = c.id
        """
    )

    # Keep the newest invitation that still works as the household's code.
    op.execute(
        """
        UPDATE app.households h
        SET invite_code = i.code, invite_expires_at = i.expires_at
        FROM (
            SELECT DISTINCT ON (household_id) household_id, code, expires_at
            FROM app.invitations
            WHERE revoked_at IS NULL AND expires_at > now() AND uses < max_uses
            ORDER BY household_id, created_at DESC
        ) i
        WHERE i.household_id = h.id
        """
    )


def _drop_dead_columns() -> None:
    op.drop_constraint(op.f("ck_households_currency_eur"), "households", schema="app")
    op.drop_column("households", "currency", schema="app")
    op.drop_column("households", "version", schema="app")
    op.drop_column("household_members", "display_name_override", schema="app")

    op.drop_index(
        "ix_expenses_household_period_live",
        table_name="expenses",
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL AND status = 'confirmed'"),
    )
    op.drop_constraint(op.f("ck_expenses_currency_eur"), "expenses", schema="app")
    op.drop_constraint(op.f("ck_expenses_status"), "expenses", schema="app")
    for column in ("currency", "status", "source_transcript", "recurring_expense_id"):
        op.drop_column("expenses", column, schema="app")
    op.create_index(
        "ix_expenses_household_period_live",
        "expenses",
        ["household_id", "period_id"],
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


# ============================================================================= downgrade


def downgrade() -> None:
    """Restore the 0004 structure. See the module docstring for what comes back."""
    _restore_procrastinate()
    op.execute("DROP TRIGGER IF EXISTS history_append_only ON app.history")
    op.execute("DROP FUNCTION IF EXISTS app.trg_history_append_only()")

    _restore_dead_columns()
    _recreate_old_tables()
    _migrate_data_backwards()

    op.drop_table("history", schema="app")
    op.drop_column("categories", "split_rule", schema="app")
    op.drop_constraint(op.f("ck_households_invite_code_length"), "households", schema="app")
    op.drop_constraint(op.f("uq_households_invite_code"), "households", schema="app")
    for column in ("split_rule", "invite_expires_at", "invite_code"):
        op.drop_column("households", column, schema="app")

    op.execute(OLD_APPEND_ONLY_SQL)
    for table in OLD_TABLES:
        op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        GRANTS_SQL.format(
            extra=(
                "REVOKE UPDATE, DELETE ON app.expense_revisions FROM split_api; "
                "REVOKE DELETE ON app.settlement_snapshots FROM split_api;"
            )
        )
    )


def _restore_procrastinate() -> None:
    # Same steps as migration 0002's upgrade.
    op.execute("SET LOCAL search_path TO app, public")
    sql = PROCRASTINATE_SCHEMA_FILE.read_text(encoding="utf-8")
    op.get_bind().connection.driver_connection.execute(sql)  # type: ignore[union-attr]
    for table in (
        "procrastinate_jobs",
        "procrastinate_periodic_defers",
        "procrastinate_events",
        "procrastinate_workers",
    ):
        op.execute(f"ALTER TABLE IF EXISTS app.{table} ENABLE ROW LEVEL SECURITY")
    op.execute("SET LOCAL search_path TO DEFAULT")


def _restore_dead_columns() -> None:
    op.add_column(
        "households",
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
        schema="app",
    )
    op.create_check_constraint(
        op.f("ck_households_currency_eur"), "households", "currency = 'EUR'", schema="app"
    )
    op.add_column(
        "households",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        schema="app",
    )
    op.add_column(
        "household_members",
        sa.Column("display_name_override", sa.String(length=80), nullable=True),
        schema="app",
    )

    op.drop_index(
        "ix_expenses_household_period_live",
        table_name="expenses",
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.add_column(
        "expenses",
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
        schema="app",
    )
    op.add_column(
        "expenses",
        sa.Column("status", sa.String(length=16), server_default="confirmed", nullable=False),
        schema="app",
    )
    op.add_column(
        "expenses", sa.Column("source_transcript", sa.Text(), nullable=True), schema="app"
    )
    op.add_column(
        "expenses", sa.Column("recurring_expense_id", sa.Uuid(), nullable=True), schema="app"
    )
    op.create_check_constraint(
        op.f("ck_expenses_currency_eur"), "expenses", "currency = 'EUR'", schema="app"
    )
    op.create_check_constraint(
        op.f("ck_expenses_status"), "expenses", "status IN ('draft', 'confirmed')", schema="app"
    )
    op.create_index(
        "ix_expenses_household_period_live",
        "expenses",
        ["household_id", "period_id"],
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL AND status = 'confirmed'"),
    )


def _timestamps() -> list[sa.Column[Any]]:
    return [
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
    ]


def _created_at() -> sa.Column[Any]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _recreate_old_tables() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_idempotency_keys_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint("user_id", "key", name=op.f("uq_idempotency_keys_user_id_key")),
        schema="app",
    )
    op.create_index(
        "ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"], schema="app"
    )
    op.create_table(
        "push_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expo_token", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        _created_at(),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("platform IN ('android', 'ios')", name=op.f("ck_push_tokens_platform")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_push_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_tokens")),
        sa.UniqueConstraint("expo_token", name=op.f("uq_push_tokens_expo_token")),
        schema="app",
    )
    op.create_index(op.f("ix_push_tokens_user_id"), "push_tokens", ["user_id"], schema="app")
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=True),
        sa.Column("entity", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["app.users.id"], name=op.f("fk_audit_log_actor_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["app.households.id"],
            name=op.f("fk_audit_log_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
        schema="app",
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity", "entity_id"], schema="app")
    op.create_index(op.f("ix_audit_log_household_id"), "audit_log", ["household_id"], schema="app")
    op.create_table(
        "household_spreadsheets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("spreadsheet_id", sa.String(length=128), nullable=False),
        sa.Column("drive_file_id", sa.String(length=128), nullable=False),
        sa.Column("shared_with", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["app.households.id"],
            name=op.f("fk_household_spreadsheets_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_household_spreadsheets")),
        sa.UniqueConstraint("household_id", name=op.f("uq_household_spreadsheets_household_id")),
        schema="app",
    )
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _created_at(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer(), server_default="5", nullable=False),
        sa.Column("uses", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_period", sa.String(length=8), nullable=True),
        sa.CheckConstraint(
            "start_period IS NULL OR start_period IN ('current', 'next')",
            name=op.f("ck_invitations_start_period"),
        ),
        sa.CheckConstraint("char_length(code) = 8", name=op.f("ck_invitations_code_length")),
        sa.CheckConstraint("max_uses BETWEEN 1 AND 50", name=op.f("ck_invitations_max_uses_range")),
        sa.CheckConstraint(
            "uses >= 0 AND uses <= max_uses", name=op.f("ck_invitations_uses_range")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app.users.id"], name=op.f("fk_invitations_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["app.households.id"],
            name=op.f("fk_invitations_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.UniqueConstraint("code", name=op.f("uq_invitations_code")),
        schema="app",
    )
    op.create_index(
        op.f("ix_invitations_household_id"), "invitations", ["household_id"], schema="app"
    )
    op.create_table(
        "settlement_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=24), nullable=False),
        sa.Column("balances", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("transfers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        _created_at(),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "trigger IN ('close', 'edit_after_close', 'reopen_close')",
            name=op.f("ck_settlement_snapshots_trigger"),
        ),
        sa.CheckConstraint("seq >= 1", name=op.f("ck_settlement_snapshots_seq_positive")),
        sa.ForeignKeyConstraint(
            ["period_id", "household_id"],
            ["app.periods.id", "app.periods.household_id"],
            name=op.f("fk_settlement_snapshots_period_id_household_id_periods"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settlement_snapshots")),
        sa.UniqueConstraint(
            "id", "household_id", name=op.f("uq_settlement_snapshots_id_household_id")
        ),
        sa.UniqueConstraint("period_id", "seq", name=op.f("uq_settlement_snapshots_period_id_seq")),
        schema="app",
    )
    op.create_table(
        "sheet_tabs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        sa.Column("sheet_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'synced', 'error')", name=op.f("ck_sheet_tabs_status")
        ),
        sa.ForeignKeyConstraint(
            ["period_id", "household_id"],
            ["app.periods.id", "app.periods.household_id"],
            name=op.f("fk_sheet_tabs_period_id_household_id_periods"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sheet_tabs")),
        sa.UniqueConstraint("period_id", name=op.f("uq_sheet_tabs_period_id")),
        schema="app",
    )
    op.create_index(
        op.f("ix_sheet_tabs_household_id"), "sheet_tabs", ["household_id"], schema="app"
    )
    op.create_table(
        "split_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("recurring_expense_id", sa.Uuid(), nullable=True),
        sa.Column("split_type", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "(scope = 'category') = (category_id IS NOT NULL)",
            name=op.f("ck_split_rules_category_scope"),
        ),
        sa.CheckConstraint(
            "(scope = 'recurring') = (recurring_expense_id IS NOT NULL)",
            name=op.f("ck_split_rules_recurring_scope"),
        ),
        sa.CheckConstraint(
            "scope IN ('household_default', 'category', 'recurring')",
            name=op.f("ck_split_rules_scope"),
        ),
        sa.CheckConstraint(
            "split_type IN ('equal', 'weights', 'percentages', 'exact', 'single', 'personal')",
            name=op.f("ck_split_rules_split_type"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id", "household_id"],
            ["app.categories.id", "app.categories.household_id"],
            name=op.f("fk_split_rules_category_id_household_id_categories"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["app.households.id"],
            name=op.f("fk_split_rules_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app.users.id"], name=op.f("fk_split_rules_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_split_rules")),
        sa.UniqueConstraint("id", "household_id", name=op.f("uq_split_rules_id_household_id")),
        schema="app",
    )
    for name, column, where in (
        ("uq_split_rules_category", "category_id", "scope = 'category'"),
        ("uq_split_rules_household_default", "household_id", "scope = 'household_default'"),
        ("uq_split_rules_recurring", "recurring_expense_id", "scope = 'recurring'"),
    ):
        op.create_index(
            name,
            "split_rules",
            [column],
            unique=True,
            schema="app",
            postgresql_where=sa.text(where),
        )
    op.create_table(
        "expense_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("expense_id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=280), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        _created_at(),
        sa.CheckConstraint(
            "action IN ('create', 'update', 'delete', 'restore', 'confirm')",
            name=op.f("ck_expense_revisions_action"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app.users.id"],
            name=op.f("fk_expense_revisions_actor_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["expense_id", "household_id"],
            ["app.expenses.id", "app.expenses.household_id"],
            name=op.f("fk_expense_revisions_expense_id_household_id_expenses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expense_revisions")),
        sa.UniqueConstraint(
            "expense_id", "version", name=op.f("uq_expense_revisions_expense_id_version")
        ),
        schema="app",
    )
    op.create_table(
        "split_rule_shares",
        sa.Column("split_rule_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("sort_key", sa.Integer(), server_default="0", nullable=False),
        sa.Column("weight", sa.Integer(), nullable=True),
        sa.Column("basis_points", sa.Integer(), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "amount_cents IS NULL OR amount_cents >= 0",
            name=op.f("ck_split_rule_shares_amount_non_negative"),
        ),
        sa.CheckConstraint(
            "basis_points IS NULL OR basis_points BETWEEN 0 AND 10000",
            name=op.f("ck_split_rule_shares_basis_points_range"),
        ),
        sa.CheckConstraint(
            "weight IS NULL OR weight >= 0", name=op.f("ck_split_rule_shares_weight_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["member_id", "household_id"],
            ["app.household_members.id", "app.household_members.household_id"],
            name=op.f("fk_split_rule_shares_member_id_household_id_household_members"),
        ),
        sa.ForeignKeyConstraint(
            ["split_rule_id", "household_id"],
            ["app.split_rules.id", "app.split_rules.household_id"],
            name=op.f("fk_split_rule_shares_split_rule_id_household_id_split_rules"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("split_rule_id", "member_id", name=op.f("pk_split_rule_shares")),
        schema="app",
    )
    op.add_column(
        "settlement_transfers", sa.Column("snapshot_id", sa.Uuid(), nullable=True), schema="app"
    )


def _migrate_data_backwards() -> None:
    # One approximate snapshot per period that has transfers, owning all of them.
    op.execute(
        """
        INSERT INTO app.settlement_snapshots
            (id, household_id, period_id, seq, trigger, balances, transfers, input_hash,
             created_at)
        SELECT gen_random_uuid(), t.household_id, t.period_id, 1, 'close', '[]'::jsonb,
               coalesce(
                   jsonb_agg(jsonb_build_object(
                       'from_member_id', t.from_member_id,
                       'to_member_id', t.to_member_id,
                       'amount_cents', t.amount_cents
                   )) FILTER (WHERE t.status <> 'cancelled'),
                   '[]'::jsonb
               ),
               '', min(t.created_at)
        FROM app.settlement_transfers t
        GROUP BY t.household_id, t.period_id
        """
    )
    op.execute(
        """
        UPDATE app.settlement_transfers t SET snapshot_id = s.id
        FROM app.settlement_snapshots s
        WHERE s.period_id = t.period_id AND s.household_id = t.household_id
        """
    )
    op.alter_column("settlement_transfers", "snapshot_id", nullable=False, schema="app")
    op.create_foreign_key(
        op.f("fk_settlement_transfers_snapshot_id_household_id_settlement_snapshots"),
        "settlement_transfers",
        "settlement_snapshots",
        ["snapshot_id", "household_id"],
        ["id", "household_id"],
        source_schema="app",
        referent_schema="app",
        ondelete="CASCADE",
    )

    # Rules back into rows.
    op.execute(
        """
        CREATE TEMP TABLE rule_src ON COMMIT DROP AS
        SELECT gen_random_uuid() AS rule_id, h.id AS household_id,
               'household_default'::text AS scope, NULL::uuid AS category_id,
               h.split_rule AS spec
        FROM app.households h
        UNION ALL
        SELECT gen_random_uuid(), c.household_id, 'category', c.id, c.split_rule
        FROM app.categories c
        WHERE c.split_rule IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO app.split_rules (id, household_id, scope, category_id, split_type)
        SELECT rule_id, household_id, scope, category_id, spec->>'split_type' FROM rule_src
        """
    )
    op.execute(
        """
        INSERT INTO app.split_rule_shares
            (split_rule_id, member_id, household_id, sort_key, weight, basis_points,
             amount_cents)
        SELECT r.rule_id, (e.value->>'member_id')::uuid, r.household_id, e.ord - 1,
               (e.value->>'weight')::int, (e.value->>'basis_points')::int,
               (e.value->>'amount_cents')::bigint
        FROM rule_src r,
             jsonb_array_elements(coalesce(r.spec->'shares', '[]'::jsonb))
                 WITH ORDINALITY AS e(value, ord)
        """
    )

    # History back into revisions (expenses) and the audit log (everything else).
    op.execute(
        """
        INSERT INTO app.expense_revisions
            (id, expense_id, household_id, version, action, actor_user_id, reason, before,
             after, created_at)
        SELECT h.id, h.entity_id, h.household_id, h.version, h.action, h.actor_user_id,
               h.reason, h.before, h.after, h.created_at
        FROM app.history h
        JOIN app.expenses e ON e.id = h.entity_id AND e.household_id = h.household_id
        WHERE h.entity = 'expense' AND h.version IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO app.audit_log
            (id, household_id, entity, entity_id, actor_user_id, action, diff, created_at)
        SELECT id, household_id, entity, entity_id, actor_user_id, action,
               coalesce(after, '{}'::jsonb), created_at
        FROM app.history
        WHERE entity <> 'expense'
        """
    )

    # The household code becomes an invitation again.
    op.execute(
        """
        INSERT INTO app.invitations (id, household_id, code, created_by, expires_at)
        SELECT gen_random_uuid(), h.id, h.invite_code, h.created_by, h.invite_expires_at
        FROM app.households h
        WHERE h.invite_code IS NOT NULL AND h.invite_expires_at IS NOT NULL
        """
    )
