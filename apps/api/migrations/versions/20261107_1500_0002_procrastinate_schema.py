"""Procrastinate job-queue schema (pinned to procrastinate 3.10.0) inside `app`.

The SQL is a frozen copy of `procrastinate/sql/schema.sql` from the pinned version
(migrations/sql/procrastinate_3.10.0_schema.sql). Upgrading Procrastinate requires a new
migration that applies the library's own migration files from that version onwards.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07 15:00:00+00:00
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_FILE = Path(__file__).resolve().parents[1] / "sql" / "procrastinate_3.10.0_schema.sql"

DROP_SQL = """
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


def upgrade() -> None:
    # Procrastinate's SQL uses unqualified names: create everything inside `app`.
    op.execute("SET LOCAL search_path TO app, public")
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    # Use the raw psycopg connection: the script has many statements and `%` characters.
    op.get_bind().connection.driver_connection.execute(sql)  # type: ignore[union-attr]
    for table in ("procrastinate_jobs", "procrastinate_periodic_defers", "procrastinate_events"):
        op.execute(f"ALTER TABLE IF EXISTS app.{table} ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE IF EXISTS app.procrastinate_workers ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'split_api') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO split_api;
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO split_api;
                GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO split_api;
            END IF;
        END $$;
        """
    )
    op.execute("SET LOCAL search_path TO DEFAULT")


def downgrade() -> None:
    op.execute(DROP_SQL)
