"""Sentry error reporting, shared by the API and the standalone worker."""

from __future__ import annotations

from uuid import UUID

import sentry_sdk

from split_ranch.core.logging import hash_user_id
from split_ranch.core.settings import Settings


def init_sentry(settings: Settings) -> bool:
    """Initialise Sentry when a DSN is configured; returns whether it was enabled.

    Calling it twice (API with the in-process worker) just rebinds the same client config.
    """
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.sentry_release,
        # No headers, cookies, IPs or request bodies with personal data (docs/08).
        send_default_pii=False,
        # Errors only: tracing would consume the free plan's quota.
        traces_sample_rate=0.0,
    )
    return True


def set_sentry_user(user_id: UUID) -> None:
    """Attach the pseudonymised user id (never the email) to the current request's events."""
    sentry_sdk.set_user({"id": hash_user_id(user_id)})
