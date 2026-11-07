"""Procrastinate app for the worker process.

Run with:  procrastinate --app=split_ranch.jobs.app.app worker
The worker needs a session-mode/direct connection (LISTEN/NOTIFY): DATABASE_URL_SESSION.
"""

from __future__ import annotations

from functools import cache

import procrastinate
import structlog
from sqlalchemy.orm import Session, sessionmaker

from split_ranch.core.db import create_db_engine, create_session_factory
from split_ranch.core.logging import configure_logging
from split_ranch.core.settings import get_settings, libpq_url
from split_ranch.use_cases import idempotency, periods

log = structlog.get_logger(__name__)


def _connector() -> procrastinate.PsycopgConnector:
    settings = get_settings()
    # Procrastinate's tables live in `app`; its SQL uses unqualified names.
    return procrastinate.PsycopgConnector(
        conninfo=libpq_url(settings.session_database_url),
        kwargs={"options": "-c search_path=app,public"},
    )


configure_logging(get_settings().log_level, get_settings().log_json)

app = procrastinate.App(connector=_connector(), import_paths=["split_ranch.jobs.app"])


@cache
def _session_factory() -> sessionmaker[Session]:
    settings = get_settings()
    engine_settings = settings.model_copy(update={"database_url": settings.session_database_url})
    return create_session_factory(create_db_engine(engine_settings))


@app.periodic(cron="*/15 * * * *", periodic_id="auto_close")
@app.task(queue="periodic", queueing_lock="auto_close_due_periods", pass_context=False)
def auto_close_due_periods(timestamp: int) -> int:
    """Close every open period whose closes_at passed (system actor)."""
    with _session_factory()() as session:
        closed = periods.auto_close_due_periods(session)
    log.info("auto_close_done", closed=closed, timestamp=timestamp)
    return closed


@app.periodic(cron="17 * * * *", periodic_id="purge_idempotency")
@app.task(queue="periodic", pass_context=False)
def purge_idempotency_keys(timestamp: int) -> int:
    with _session_factory()() as session:
        return idempotency.purge_expired(session)


@app.task(name="sync_period_tab", queue="sheets")
def sync_period_tab(household_id: str, period_id: str) -> None:
    """Google Sheets sync: not implemented in this phase (enqueued so nothing is lost)."""
    log.info("sheets_sync_not_implemented", household_id=household_id, period_id=period_id)


@app.task(name="notify_period_closed", queue="push")
def notify_period_closed(household_id: str, period_id: str) -> None:
    """Push notification: not implemented in this phase."""
    log.info("push_not_implemented", household_id=household_id, period_id=period_id)
