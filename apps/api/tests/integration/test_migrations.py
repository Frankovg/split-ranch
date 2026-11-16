"""Alembic: downgrade/upgrade round trip and the empty-tables guard of 0006."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from split_ranch.core.settings import sqlalchemy_url
from tests.conftest import API_DIR


def _config(url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url(url))
    return cfg


def test_round_trip(database_url: str, engine: Engine) -> None:
    cfg = _config(database_url)
    command.downgrade(cfg, "0005")
    with engine.connect() as conn:
        # 0006 down: households, periods and settlement transfers are back, groups are gone.
        for table in ("households", "household_members", "periods", "settlement_transfers"):
            assert conn.execute(text(f"SELECT to_regclass('app.{table}')")).scalar(), table
        for table in ("groups", "group_members", "payments"):
            assert conn.execute(text(f"SELECT to_regclass('app.{table}')")).scalar() is None
    command.downgrade(cfg, "base")
    with engine.connect() as conn:
        for table in ("users", "households", "expenses", "history"):
            assert conn.execute(text(f"SELECT to_regclass('app.{table}')")).scalar() is None
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar() == "0006"
        for table in ("users", "groups", "group_members", "payments", "history"):
            assert conn.execute(text(f"SELECT to_regclass('app.{table}')")).scalar(), table
        for table in ("households", "periods", "settlement_transfers"):
            assert conn.execute(text(f"SELECT to_regclass('app.{table}')")).scalar() is None


def test_0006_refuses_non_empty_tables(database_url: str, engine: Engine) -> None:
    """D3: 0006 has no data mapping, so it must stop instead of dropping rows."""
    cfg = _config(database_url)
    command.downgrade(cfg, "0005")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO app.users (id, email) VALUES "
                    "('00000000-0000-7000-8000-000000000001', 'x@example.com')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO app.households (id, name, created_by) VALUES "
                    "('00000000-0000-7000-8000-000000000002', 'Casa', "
                    "'00000000-0000-7000-8000-000000000001')"
                )
            )
        with pytest.raises(RuntimeError, match=r"needs an empty app.households"):
            command.upgrade(cfg, "head")
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM app.households"))
            conn.execute(text("DELETE FROM app.users"))
        command.upgrade(cfg, "head")
