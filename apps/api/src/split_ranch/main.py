"""FastAPI application factory. Run with `uvicorn split_ranch.main:app`."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, Request, Response
from sqlalchemy import Engine
from starlette.concurrency import run_in_threadpool

from split_ranch.api.routers import expenses, groups, me, payments, system
from split_ranch.core.db import create_db_engine, create_session_factory
from split_ranch.core.errors import install_error_handlers
from split_ranch.core.logging import configure_logging
from split_ranch.core.observability import init_sentry
from split_ranch.core.rate_limit import RateLimiter
from split_ranch.core.security import TokenVerifier
from split_ranch.core.settings import Settings, get_settings
from split_ranch.integrations.expo_push import ExpoPushClient
from split_ranch.integrations.supabase_admin import AuthAdmin, SupabaseAuthAdmin

log = structlog.get_logger(__name__)

API_PREFIX = "/v1"
# A client request id is echoed in the response, the logs and Sentry: keep it short and plain.
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9-]{1,64}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Fetch the JWKS before the first request instead of during it (blocking urllib).
    verifier: TokenVerifier = app.state.token_verifier
    await run_in_threadpool(verifier.preload)
    yield
    # Uvicorn has finished the in-flight requests (and their background pushes) by now.
    closers: list[tuple[str, Callable[[], None]]] = app.state.shutdown_closers
    for name, close in closers:
        try:
            await run_in_threadpool(close)
        except Exception:
            log.exception("shutdown_close_failed", resource=name)


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    token_verifier: TokenVerifier | None = None,
    push_client: ExpoPushClient | None = None,
    auth_admin: AuthAdmin | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_sentry(settings)

    app = FastAPI(
        title="Splitranch",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs" if settings.app_env != "prod" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    # Only what the app creates itself is closed on shutdown; injected objects (tests share
    # one engine across apps) belong to the caller.
    closers: list[tuple[str, Callable[[], None]]] = []
    app.state.shutdown_closers = closers
    if engine is None:
        engine = create_db_engine(settings)
        closers.append(("db_engine", engine.dispose))
    app.state.engine = engine
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.token_verifier = token_verifier or TokenVerifier(
        jwks_url=settings.jwks_url,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        leeway_seconds=settings.jwt_leeway_seconds,
        cache_seconds=settings.jwks_cache_seconds,
        max_stale_seconds=settings.jwks_max_stale_seconds,
    )

    # None turns push notifications off (no request ever reaches Expo).
    if push_client is None and settings.push_enabled:
        push_client = ExpoPushClient(
            access_token=settings.expo_access_token,
            timeout_seconds=settings.push_timeout_seconds,
        )
        closers.append(("expo_push_client", push_client.close))
    app.state.push_client = push_client

    # Account deletion needs the secret key; without it DELETE /me answers 503.
    if auth_admin is None and settings.supabase_secret_key:
        auth_admin = SupabaseAuthAdmin(
            supabase_url=settings.supabase_url, secret_key=settings.supabase_secret_key
        )
    app.state.auth_admin = auth_admin

    app.state.user_rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    app.state.invite_rate_limiter = RateLimiter(settings.invite_rate_limit_per_minute)

    install_error_handlers(app)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", "")
        if not REQUEST_ID_PATTERN.fullmatch(request_id):
            request_id = uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        # Lets a Sentry event be matched with the request's log lines.
        sentry_sdk.set_tag("request_id", request_id)
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Min-App-Version"] = settings.min_app_version
        # User and group bound by the auth dependencies (see api.deps.bind_log_context).
        log_context: dict[str, str] = getattr(request.state, "log_context", {})
        log.info(
            "request",
            **log_context,
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
