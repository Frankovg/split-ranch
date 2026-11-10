"""FastAPI application factory. Run with `uvicorn split_ranch.main:app`."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from sqlalchemy import Engine

from split_ranch.api.routers import expenses, households, me, periods, system
from split_ranch.core.db import create_db_engine, create_session_factory
from split_ranch.core.errors import install_error_handlers
from split_ranch.core.logging import configure_logging
from split_ranch.core.security import TokenVerifier
from split_ranch.core.settings import Settings, get_settings

log = structlog.get_logger(__name__)

API_PREFIX = "/v1"


# TODO: Ver esto de Sentry
def _init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        send_default_pii=False,
        traces_sample_rate=0.0,
    )


WORKER_SHUTDOWN_TIMEOUT_SECONDS = 20

# TODO: Ver este deprecado
@asynccontextmanager
async def _in_process_worker() -> AsyncIterator[None]:
    """Run the Procrastinate worker as a task of the API's event loop.

    Imported lazily: the jobs module builds its connector from the settings at import time.
    """
    from split_ranch.jobs.app import app as job_app

    async with job_app.open_async():
        worker = asyncio.create_task(job_app.run_worker_async(install_signal_handlers=False))
        log.info("in_process_worker_started")
        try:
            yield
        finally:
            worker.cancel()
            try:
                await asyncio.wait_for(worker, timeout=WORKER_SHUTDOWN_TIMEOUT_SECONDS)
            except asyncio.CancelledError:
                log.info("in_process_worker_stopped")
            except TimeoutError:
                # Jobs left in `doing` are picked up by retry_stalled_jobs on the next start.
                log.warning("in_process_worker_stopped_ungracefully")


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    token_verifier: TokenVerifier | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    _init_sentry(settings)
    run_worker = settings.run_worker_in_api

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if not run_worker:
            yield
            return
        async with _in_process_worker():
            yield

    app = FastAPI(
        title="Split Ranch",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs" if settings.app_env != "prod" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine or create_db_engine(settings)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.token_verifier = token_verifier or TokenVerifier(
        jwks_url=settings.jwks_url,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        leeway_seconds=settings.jwt_leeway_seconds,
        cache_seconds=settings.jwks_cache_seconds,
    )

    install_error_handlers(app)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Min-App-Version"] = settings.min_app_version
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
        )
        return response

    # Health endpoints live at the root (platform probes) and under /v1.
    app.include_router(system.router, include_in_schema=False)
    for router in (
        system.router,
        me.router,
        households.router,
        expenses.router,
        periods.router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    return app


def __getattr__(name: str) -> FastAPI:
    """Lazy `app` so importing this module does not read settings or create an engine."""
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(name)
