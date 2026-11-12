"""Supabase access-token verification against the project JWKS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

import jwt
import structlog

from split_ranch.core.errors import TokenExpired, Unauthenticated

log = structlog.get_logger(__name__)

# Only asymmetric algorithms: HS256 (shared secret) and "none" are always rejected.
ALLOWED_ALGORITHMS = ("ES256", "ES384", "ES512", "RS256", "RS384", "RS512", "PS256", "EdDSA")
MAX_KID_LENGTH = 128


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
        key_source: SigningKeySource | None = None,
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.leeway = leeway_seconds
        # The key set is cached for `cache_seconds`, so a key revoked in Supabase stops being
        # trusted once it expires. The per-key LRU cache (`cache_keys`) stays off: it never
        # expires. An unknown `kid` forces a refetch at most once per cooldown, so tokens
        # with random `kid` values cannot flood the JWKS endpoint (PyJWT >= 2.14).
        self.key_source: SigningKeySource = key_source or jwt.PyJWKClient(
            jwks_url,
            cache_keys=False,
            lifespan=cache_seconds,
            cooldown_duration=refetch_cooldown_seconds,
            timeout=5,
        )

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
