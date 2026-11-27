"""Supabase access-token verification against the project JWKS."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

import jwt
import structlog
from jwt import PyJWKSet

from split_ranch.core.errors import ServiceUnavailable, TokenExpired, Unauthenticated

log = structlog.get_logger(__name__)

# Only asymmetric algorithms: HS256 (shared secret) and "none" are always rejected.
ALLOWED_ALGORITHMS = ("ES256", "ES384", "ES512", "RS256", "RS384", "RS512", "PS256", "EdDSA")
MAX_KID_LENGTH = 128
# Seconds a client should wait after `503 auth_unavailable`.
AUTH_RETRY_AFTER_SECONDS = 30


class ResilientJWKClient(jwt.PyJWKClient):
    """PyJWKClient that survives a JWKS outage.

    When a refetch fails (network error, timeout, HTTP error) it serves the last key set
    that was fetched successfully, up to `max_stale_seconds` after that fetch. PyJWKClient
    caches what it is given again for its `lifespan`, so the endpoint is retried once per
    lifespan instead of on every request (each attempt would hold the client lock for up
    to `timeout` seconds). With nothing to serve, failures are remembered for
    `failure_backoff_seconds` and fail fast instead of queueing behind the lock.
    """

    def __init__(
        self,
        uri: str,
        *,
        max_stale_seconds: float,
        failure_backoff_seconds: float = 5,
        **kwargs: Any,
    ) -> None:
        super().__init__(uri, **kwargs)
        self.max_stale_seconds = max_stale_seconds
        self.failure_backoff_seconds = failure_backoff_seconds
        self._last_good: tuple[PyJWKSet, float] | None = None
        self._failing_until = 0.0

    def fetch_data(self) -> Any:
        now = time.monotonic()
        stale = self._last_good
        usable = stale if stale is not None and now - stale[1] <= self.max_stale_seconds else None
        if usable is None and now < self._failing_until:
            raise jwt.PyJWKClientConnectionError("JWKS endpoint failed recently")
        try:
            data = super().fetch_data()
        except jwt.PyJWKClientConnectionError as exc:
            if usable is None:
                self._failing_until = now + self.failure_backoff_seconds
                log.error("jwks_fetch_failed", error=str(exc), stale_available=False)
                raise
            log.warning(
                "jwks_fetch_failed",
                error=str(exc),
                stale_available=True,
                stale_age_seconds=round(now - usable[1]),
            )
            return usable[0]
        self._last_good = (PyJWKSet.from_dict(data), time.monotonic())
        self._failing_until = 0.0
        return data


class SigningKeySource(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK: ...


@dataclass(frozen=True)
class TokenClaims:
    user_id: UUID
    email: str | None
    display_name: str | None
    avatar_url: str | None
    raw: dict[str, Any] = field(repr=False)


class TokenVerifier:
    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        audience: str = "authenticated",
        leeway_seconds: int = 30,
        cache_seconds: int = 600,
        refetch_cooldown_seconds: float = 30,
        max_stale_seconds: float = 6 * 3600,
        key_source: SigningKeySource | None = None,
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.leeway = leeway_seconds
        # The key set is cached for `cache_seconds`, so a key revoked in Supabase stops being
        # trusted once it expires. The per-key LRU cache (`cache_keys`) stays off: it never
        # expires. An unknown `kid` forces a refetch at most once per cooldown, so tokens
        # with random `kid` values cannot flood the JWKS endpoint (PyJWT >= 2.14). If
        # Supabase Auth is down, the last good key set keeps being used (see
        # ResilientJWKClient), so a short outage does not log everybody out.
        self.key_source: SigningKeySource = key_source or ResilientJWKClient(
            jwks_url,
            max_stale_seconds=max_stale_seconds,
            cache_keys=False,
            lifespan=cache_seconds,
            cooldown_duration=refetch_cooldown_seconds,
            timeout=5,
        )

    def preload(self) -> None:
        """Fetch the key set ahead of the first request; a failure is only logged."""
        if not isinstance(self.key_source, jwt.PyJWKClient):
            return
        try:
            self.key_source.get_jwk_set()
        except jwt.PyJWTError as exc:
            log.warning("jwks_preload_failed", error=str(exc))

    def verify(self, token: str) -> TokenClaims:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise Unauthenticated("Malformed token") from exc
        alg = header.get("alg")
        if alg not in ALLOWED_ALGORITHMS:
            raise Unauthenticated("Unsupported token algorithm")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid or len(kid) > MAX_KID_LENGTH:
            raise Unauthenticated("Missing or invalid key id")
        try:
            signing_key = self.key_source.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientConnectionError as exc:
            # Our dependency is down, not the token: 401 would make the app refresh and
            # retry in a loop. Subclass of PyJWKClientError, so it is caught first.
            raise ServiceUnavailable(
                "Authentication is temporarily unavailable",
                code="auth_unavailable",
                headers={"Retry-After": str(AUTH_RETRY_AFTER_SECONDS)},
            ) from exc
        except jwt.PyJWKClientError as exc:
            raise Unauthenticated("Unknown signing key") from exc
        except jwt.PyJWTError as exc:
            raise Unauthenticated("Invalid token") from exc
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=signing_key.key,
                algorithms=[alg],
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.leeway,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpired() from exc
        except jwt.PyJWTError as exc:
            raise Unauthenticated("Invalid token") from exc

        if claims.get("role") != "authenticated":
            raise Unauthenticated("Token role not allowed")
        # Anonymous users also get the `authenticated` role; only this claim tells them apart.
        # Rejected here too, not only by `enable_anonymous_sign_ins = false` in Supabase.
        # Fails closed: only a missing claim or a literal `false` is a permanent account.
        if claims.get("is_anonymous", False) is not False:
            raise Unauthenticated("Anonymous accounts are not allowed")
        try:
            user_id = UUID(str(claims["sub"]))
        except ValueError as exc:
            raise Unauthenticated("Invalid subject") from exc

        metadata = claims.get("user_metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        display_name = metadata.get("full_name") or metadata.get("name")
        return TokenClaims(
            user_id=user_id,
            email=claims.get("email") or None,
            display_name=str(display_name) if display_name else None,
            avatar_url=metadata.get("avatar_url") or metadata.get("picture"),
            raw=claims,
        )
