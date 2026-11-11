"""Alembic: downgrade/upgrade round trip and no pending autogenerate diff."""

from __future__ import annotations

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


def test_round_trip_and_check(database_url: str, engine: Engine) -> None:
    cfg = _config(database_url)
    command.check(cfg)  # raises if models and migrations diverge
    command.downgrade(cfg, "0004")
    with engine.connect() as conn:
        # 0005 down: the old tables and the job queue are back, the merged ones are gone.
        for table in ("split_rules", "expense_revisions", "invitations", "procrastinate_jobs"):
            assert conn.execute(text(f"SELECT to_regclass('app.{table}')")).scalar(), table
        assert conn.execute(text("SELECT to_regclass('app.history')")).scalar() is None
    command.downgrade(cfg, "0003")
    with engine.connect() as conn:
        # 0004 down: the (empty) Quick split tables and the payment columns are back.
        assert conn.execute(text("SELECT to_regclass('app.quick_events')")).scalar()
        assert conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'app' "
                "AND table_name = 'users' AND column_name = 'payment_handles'"
            )
        ).scalar()
    command.downgrade(cfg, "0002")
    with engine.connect() as conn:
        # 0003 down: periods are calendar months again.
        assert conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = 'app' AND table_name = 'periods' AND column_name = 'month'"
            )
        ).scalar()
    command.downgrade(cfg, "0001")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('app.procrastinate_jobs')")).scalar() is None
    command.downgrade(cfg, "base")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('app.expenses')")).scalar() is None
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar() == "0005"
        assert conn.execute(text("SELECT to_regclass('app.procrastinate_jobs')")).scalar() is None
        assert conn.execute(text("SELECT to_regclass('app.quick_events')")).scalar() is None
        assert conn.execute(text("SELECT to_regclass('app.history')")).scalar()
