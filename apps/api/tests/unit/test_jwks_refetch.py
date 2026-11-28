"""TokenVerifier with a real PyJWKClient: JWKS refetch limits, rotation and revocation.

Only the HTTP layer and the monotonic clock are faked, so these tests break if the PyJWT
version in use stops rate-limiting refetches triggered by unknown `kid` values.
"""

from __future__ import annotations

import io
import json
import types
import urllib.error
import uuid
from typing import Any

import jwt
import jwt.api_jwk
import jwt.jwk_set_cache
import jwt.jwks_client
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from split_ranch.core import security
from split_ranch.core.errors import ServiceUnavailable, Unauthenticated
from split_ranch.core.security import TokenVerifier
from split_ranch.core.settings import Settings
from split_ranch.main import create_app
from tests.conftest import ISSUER, SigningKey, make_token

JWKS_URL = "https://test-project.supabase.co/auth/v1/.well-known/jwks.json"


class FakeJWKSEndpoint:
    """Serves the current key set to PyJWKClient and counts the fetches."""

    def __init__(self, keys: list[SigningKey]) -> None:
        self.keys = keys
        self.fetches = 0
        self.down = False  # True: every fetch fails like an unreachable Supabase Auth

    def open(self, request: Any, timeout: float | None = None) -> io.BytesIO:
        self.fetches += 1
        if self.down:
            raise urllib.error.URLError("connection refused")
        body = json.dumps({"keys": [k.jwk for k in self.keys]}).encode()
        return io.BytesIO(body)


class FakeMonotonic:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def endpoint(monkeypatch: pytest.MonkeyPatch, signing_key: SigningKey) -> FakeJWKSEndpoint:
    fake = FakeJWKSEndpoint([signing_key])
    monkeypatch.setattr(jwt.jwks_client.urllib.request, "build_opener", lambda *_: fake)
    return fake


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeMonotonic:
    fake = FakeMonotonic()
    fake_time = types.SimpleNamespace(monotonic=fake)
    for module in (jwt.jwks_client, jwt.jwk_set_cache, jwt.api_jwk, security):
        monkeypatch.setattr(module, "time", fake_time)
    return fake


@pytest.fixture
def verifier(endpoint: FakeJWKSEndpoint, clock: FakeMonotonic) -> TokenVerifier:
    return TokenVerifier(
        jwks_url=JWKS_URL, issuer=ISSUER, cache_seconds=600, refetch_cooldown_seconds=30
    )


def test_unknown_kids_do_not_flood_the_jwks_endpoint(
    verifier: TokenVerifier, endpoint: FakeJWKSEndpoint, signing_key: SigningKey
) -> None:
    verifier.verify(make_token(signing_key, uuid.uuid4()))
    assert endpoint.fetches == 1

    for _ in range(50):
        with pytest.raises(Unauthenticated):
            verifier.verify(make_token(signing_key, uuid.uuid4(), kid=uuid.uuid4().hex))
    assert endpoint.fetches == 1

    # Legitimate tokens keep working from the cache.
    verifier.verify(make_token(signing_key, uuid.uuid4()))
    assert endpoint.fetches == 1


def test_unknown_kids_refetch_at_most_once_per_cooldown(
    verifier: TokenVerifier,
    endpoint: FakeJWKSEndpoint,
    clock: FakeMonotonic,
    signing_key: SigningKey,
) -> None:
    verifier.verify(make_token(signing_key, uuid.uuid4()))
    for _ in range(10):
        clock.advance(31)
        for _ in range(20):
            with pytest.raises(Unauthenticated):
                verifier.verify(make_token(signing_key, uuid.uuid4(), kid=uuid.uuid4().hex))
    # The initial fetch plus one per elapsed cooldown, not one per token.
    assert endpoint.fetches == 11


def test_rotated_key_is_picked_up_after_the_cooldown(
    verifier: TokenVerifier,
    endpoint: FakeJWKSEndpoint,
    clock: FakeMonotonic,
    signing_key: SigningKey,
) -> None:
    verifier.verify(make_token(signing_key, uuid.uuid4()))
    new_key = SigningKey("rotated-key", ec.generate_private_key(ec.SECP256R1()))
    endpoint.keys = [signing_key, new_key]

    clock.advance(31)
    claims = verifier.verify(make_token(new_key, uuid.uuid4()))
    assert claims.user_id
    assert endpoint.fetches == 2


def test_revoked_key_stops_being_trusted_when_the_cache_expires(
    verifier: TokenVerifier,
    endpoint: FakeJWKSEndpoint,
    clock: FakeMonotonic,
    signing_key: SigningKey,
) -> None:
    verifier.verify(make_token(signing_key, uuid.uuid4()))
    endpoint.keys = [SigningKey("replacement", ec.generate_private_key(ec.SECP256R1()))]

    clock.advance(601)
    with pytest.raises(Unauthenticated):
        verifier.verify(make_token(signing_key, uuid.uuid4()))


# A non-string `kid` is already rejected by PyJWT when parsing the header.
@pytest.mark.parametrize("kid", [None, "", "k" * 129])
def test_missing_or_invalid_kid_is_rejected_without_fetching(
    verifier: TokenVerifier, endpoint: FakeJWKSEndpoint, signing_key: SigningKey, kid: Any
) -> None:
    headers = {} if kid is None else {"kid": kid}
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "iss": ISSUER,
            "aud": "authenticated",
            "role": "authenticated",
            "exp": 4_000_000_000,
        },
        signing_key.private,
        algorithm="ES256",
        headers=headers,
    )
    with pytest.raises(Unauthenticated):
        verifier.verify(token)
    assert endpoint.fetches == 0


# ------------------------------------------------------------- JWKS outages (S1)


def _verifier(max_stale_seconds: float = 3600) -> TokenVerifier:
    return TokenVerifier(
        jwks_url=JWKS_URL,
        issuer=ISSUER,
        cache_seconds=600,
        refetch_cooldown_seconds=30,
        max_stale_seconds=max_stale_seconds,
    )


def test_outage_keeps_serving_the_last_good_key_set(
    endpoint: FakeJWKSEndpoint, clock: FakeMonotonic, signing_key: SigningKey
) -> None:
    verifier = _verifier()
    verifier.verify(make_token(signing_key, uuid.uuid4()))
    endpoint.down = True

    clock.advance(601)  # the cached set expired: the refetch fails
    assert verifier.verify(make_token(signing_key, uuid.uuid4())).user_id
    assert endpoint.fetches == 2

    # The stale set is cached again for a lifespan: no request waits on the dead endpoint.
    for _ in range(20):
        verifier.verify(make_token(signing_key, uuid.uuid4()))
    assert endpoint.fetches == 2

    # Back up: the next expiry fetches a fresh set again.
    endpoint.down = False
    clock.advance(601)
    verifier.verify(make_token(signing_key, uuid.uuid4()))
    assert endpoint.fetches == 3


def test_outage_longer_than_max_stale_is_503(
    endpoint: FakeJWKSEndpoint, clock: FakeMonotonic, signing_key: SigningKey
) -> None:
    verifier = _verifier(max_stale_seconds=900)
    verifier.verify(make_token(signing_key, uuid.uuid4()))
    endpoint.down = True
    clock.advance(601)
    verifier.verify(make_token(signing_key, uuid.uuid4()))  # stale, 601 s old

    clock.advance(601)  # 1202 s since the last good fetch
    with pytest.raises(ServiceUnavailable) as info:
        verifier.verify(make_token(signing_key, uuid.uuid4()))
    assert info.value.status == 503
    assert info.value.code == "auth_unavailable"
    assert info.value.headers == {"Retry-After": "30"}


def test_unreachable_jwks_without_keys_is_503_and_fails_fast(
    endpoint: FakeJWKSEndpoint, clock: FakeMonotonic, signing_key: SigningKey
) -> None:
    verifier = _verifier()
    endpoint.down = True
    for _ in range(10):
        with pytest.raises(ServiceUnavailable):
            verifier.verify(make_token(signing_key, uuid.uuid4()))
    # One real attempt; the rest fail fast during the backoff instead of queueing.
    assert endpoint.fetches == 1

    clock.advance(6)
    endpoint.down = False
    assert verifier.verify(make_token(signing_key, uuid.uuid4())).user_id
    assert endpoint.fetches == 2


def test_unknown_kid_during_outage_is_still_401(
    endpoint: FakeJWKSEndpoint, clock: FakeMonotonic, signing_key: SigningKey
) -> None:
    verifier = _verifier()
    verifier.verify(make_token(signing_key, uuid.uuid4()))
    endpoint.down = True
    clock.advance(31)
    with pytest.raises(Unauthenticated):
        verifier.verify(make_token(signing_key, uuid.uuid4(), kid="unknown-kid"))


def test_preload_fetches_once_and_tolerates_an_outage(
    endpoint: FakeJWKSEndpoint, clock: FakeMonotonic, signing_key: SigningKey
) -> None:
    verifier = _verifier()
    verifier.preload()
    assert endpoint.fetches == 1
    verifier.verify(make_token(signing_key, uuid.uuid4()))
    assert endpoint.fetches == 1

    down = _verifier()
    endpoint.down = True
    down.preload()  # only logged: the API still starts
    assert endpoint.fetches == 2


def test_app_startup_preloads_the_jwks(endpoint: FakeJWKSEndpoint, clock: FakeMonotonic) -> None:
    settings = Settings(
        app_env="test",
        supabase_url="https://test-project.supabase.co",
        sentry_dsn=None,
        supabase_secret_key=None,
        push_enabled=False,
        log_json=False,
        log_level="WARNING",
    )
    # Never connected: the engine is only created.
    engine = create_engine("postgresql+psycopg://unused@localhost:1/unused")
    app = create_app(settings, engine=engine)
    assert endpoint.fetches == 0
    with TestClient(app):
        assert endpoint.fetches == 1
