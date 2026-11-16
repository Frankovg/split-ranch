"""FastAPI application factory. Run with `uvicorn split_ranch.main:app`."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import sentry_sdk
import structlog
from fastapi import FastAPI, Request, Response
from sqlalchemy import Engine

from split_ranch.api.routers import expenses, groups, me, payments, system
from split_ranch.core.db import create_db_engine, create_session_factory
from split_ranch.core.errors import install_error_handlers
from split_ranch.core.logging import configure_logging
from split_ranch.core.observability import init_sentry
from split_ranch.core.security import TokenVerifier
from split_ranch.core.settings import Settings, get_settings

log = structlog.get_logger(__name__)

API_PREFIX = "/v1"


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    token_verifier: TokenVerifier | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_sentry(settings)

    app = FastAPI(
        title="Split Ranch",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs" if settings.app_env != "prod" else None,
        redoc_url=None,
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
        # Lets a Sentry event be matched with the request's log lines.
        sentry_sdk.set_tag("request_id", request_id)
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
        groups.router,
        expenses.router,
        payments.router,
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
