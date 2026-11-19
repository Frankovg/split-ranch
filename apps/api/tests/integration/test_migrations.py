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
        assert conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar() == "0010"
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


def test_0008_archives_the_default_other_category(database_url: str, engine: Engine) -> None:
    """0008 archives the default "Otros" (icon `dots`) and records it; others are untouched."""
    cfg = _config(database_url)
    command.downgrade(cfg, "0007")
    user, group = "00000000-0000-7000-8000-000000000011", "00000000-0000-7000-8000-000000000012"
    other, cart = "00000000-0000-7000-8000-000000000013", "00000000-0000-7000-8000-000000000014"
    try:
        with engine.begin() as conn:
            conn.execute(
                text(f"INSERT INTO app.users (id, email) VALUES ('{user}', 'y@example.com')")
            )
            conn.execute(
                text(
                    "INSERT INTO app.groups (id, name, created_by, split_rule) VALUES "
                    f"('{group}', 'Piso', '{user}', '{{\"split_type\": \"equal\"}}')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO app.categories (id, group_id, name, icon, is_default) VALUES "
                    f"('{other}', '{group}', 'Otros', 'dots', true), "
                    f"('{cart}', '{group}', 'Supermercado', 'cart', true)"
                )
            )
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            archived = dict(
                conn.execute(
                    text(
                        "SELECT id::text, archived_at IS NOT NULL FROM app.categories "
                        "WHERE icon IN ('dots', 'cart')"
                    )
                ).all()
            )
            assert archived == {other: True, cart: False}
            assert (
                conn.execute(
                    text(
                        "SELECT count(*) FROM app.history WHERE entity = 'category' "
                        f"AND action = 'archive' AND entity_id = '{other}'"
                    )
                ).scalar()
                == 1
            )
    finally:
        command.downgrade(cfg, "0007")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM app.groups"))
            conn.execute(text("DELETE FROM app.users"))
        command.upgrade(cfg, "head")


def test_0009_switches_existing_groups_to_the_new_defaults(
    database_url: str, engine: Engine
) -> None:
    """0009 archives the utility defaults and adds Insurance and Shopping once per group."""
    cfg = _config(database_url)
    command.downgrade(cfg, "0008")
    user, group = "00000000-0000-7000-8000-000000000021", "00000000-0000-7000-8000-000000000022"
    try:
        with engine.begin() as conn:
            conn.execute(
                text(f"INSERT INTO app.users (id, email) VALUES ('{user}', 'z@example.com')")
            )
            conn.execute(
                text(
                    "INSERT INTO app.groups (id, name, created_by, split_rule) VALUES "
                    f"('{group}', 'Piso', '{user}', '{{\"split_type\": \"equal\"}}')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO app.categories (group_id, id, name, icon, is_default) VALUES "
                    f"('{group}', gen_random_uuid(), 'Luz', 'bolt', true), "
                    f"('{group}', gen_random_uuid(), 'Internet', 'wifi', true), "
                    f"('{group}', gen_random_uuid(), 'Supermercado', 'cart', true), "
                    f"('{group}', gen_random_uuid(), 'shopping', 'tag', false)"
                )
            )
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT name, archived_at IS NOT NULL FROM app.categories "
                    f"WHERE group_id = '{group}' ORDER BY name"
                )
            ).all()
            # A custom "shopping" already exists, so the default Shopping is not added.
            assert {tuple(r) for r in rows} == {
                ("Insurance", False),
                ("Internet", True),
                ("Luz", True),
                ("Supermercado", False),
                ("shopping", False),
            }
            assert (
                conn.execute(
                    text(f"SELECT count(*) FROM app.history WHERE group_id = '{group}'")
                ).scalar()
                == 3
            )
    finally:
        command.downgrade(cfg, "0008")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM app.groups"))
            conn.execute(text("DELETE FROM app.users"))
        command.upgrade(cfg, "head")
