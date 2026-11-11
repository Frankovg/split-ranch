"""Alembic environment: owns only the `app` schema."""

from __future__ import annotations

from typing import Any

from alembic import context
from sqlalchemy import Connection, create_engine, pool, text

from split_ranch.core.settings import get_settings, sqlalchemy_url
from split_ranch.models import SCHEMA, Base

config = context.config
target_metadata = Base.metadata


def include_name(name: str | None, type_: str, parent_names: Any) -> bool:
    """Never look at Supabase-owned schemas: autogenerate only compares `app`."""
    if type_ == "schema":
        return name == SCHEMA
    return True


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        version_table_schema=SCHEMA,
        compare_type=True,
        literal_binds=connection is None,
    )


def _database_url() -> str:
    url = config.get_main_option("sqlalchemy.url") or context.get_x_argument(
        as_dictionary=True
    ).get("url")
    return sqlalchemy_url(url or get_settings().session_database_url)


def run_migrations_offline() -> None:
    _configure(url=_database_url())
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests may hand over an existing connection via config.attributes.
    existing = config.attributes.get("connection")
    if existing is not None:
        _run(existing)
        return
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        _run(connection)
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
