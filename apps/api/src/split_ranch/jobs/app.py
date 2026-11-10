"""Procrastinate app for the worker.

Run standalone with:  procrastinate --app=split_ranch.jobs.app.app worker
or inside the API process with RUN_WORKER_IN_API=true (free hosting, see infra/README.md).
The worker needs a session-mode/direct connection (LISTEN/NOTIFY): DATABASE_URL_SESSION.
"""

from __future__ import annotations

from functools import cache

import procrastinate
import structlog
from sqlalchemy.orm import Session, sessionmaker

from split_ranch.core.db import create_db_engine, create_session_factory
from split_ranch.core.logging import configure_logging
from split_ranch.core.observability import init_sentry
from split_ranch.core.settings import get_settings, libpq_url
from split_ranch.use_cases import idempotency

log = structlog.get_logger(__name__)


def _connector() -> procrastinate.PsycopgConnector:
    settings = get_settings()
    # Procrastinate's tables live in `app`; its SQL uses unqualified names.
    return procrastinate.PsycopgConnector(
        conninfo=libpq_url(settings.session_database_url),
        kwargs={
            "options": "-c search_path=app,public",
            # A stalled attempt against the Supabase session pooler fails fast and the
            # pool retries it, instead of hanging until the pool's own timeout.
            "connect_timeout": 10,
        },
        # psycopg_pool defaults to opening 4 connections up front; the session pooler
        # sometimes stalls on that burst. One worker (concurrency 1) needs one or two.
        min_size=1,
        max_size=4,
        timeout=60,
    )


configure_logging(get_settings().log_level, get_settings().log_json)
# The standalone worker never runs create_app; failed jobs reach Sentry through
# Procrastinate's ERROR log records (default LoggingIntegration).
init_sentry(get_settings())

app = procrastinate.App(connector=_connector(), import_paths=["split_ranch.jobs.app"])


@cache
def _session_factory() -> sessionmaker[Session]:
    settings = get_settings()
    engine_settings = settings.model_copy(update={"database_url": settings.session_database_url})
    return create_session_factory(create_db_engine(engine_settings))


@app.periodic(cron="17 * * * *", periodic_id="purge_idempotency")
@app.task(queue="periodic", pass_context=False)
def purge_idempotency_keys(timestamp: int) -> int:
    with _session_factory()() as session:
        return idempotency.purge_expired(session)


@app.periodic(cron="*/10 * * * *", periodic_id="retry_stalled_jobs")
@app.task(queue="periodic", queueing_lock="retry_stalled_jobs", pass_context=False)
async def retry_stalled_jobs(timestamp: int) -> int:
    """Requeue jobs left in `doing` by a worker that died (e.g. a free instance spun down)."""
    stalled = list(await app.job_manager.get_stalled_jobs())
    for job in stalled:
        await app.job_manager.retry_job(job)
    if stalled:
        log.warning("stalled_jobs_retried", count=len(stalled))
    return len(stalled)


@app.task(name="sync_period_tab", queue="sheets")
def sync_period_tab(household_id: str, period_id: str) -> None:
    """Google Sheets sync: not implemented in this phase (enqueued so nothing is lost)."""
    log.info("sheets_sync_not_implemented", household_id=household_id, period_id=period_id)


@app.task(name="notify_period_closed", queue="push")
def notify_period_closed(household_id: str, period_id: str) -> None:
    """Push notification: not implemented in this phase."""
    log.info("push_not_implemented", household_id=household_id, period_id=period_id)
