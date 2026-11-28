"""Shared fixtures: PostgreSQL (TEST_DATABASE_URL or pgserver), app, fake Supabase JWKS."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from split_ranch.core import clock as clock_module
from split_ranch.core.db import get_session
from split_ranch.core.security import TokenVerifier
from split_ranch.core.settings import Settings, sqlalchemy_url
from split_ranch.main import create_app

API_DIR = Path(__file__).resolve().parents[1]
ISSUER = "https://test-project.supabase.co/auth/v1"
KID = "test-key-1"


# ------------------------------------------------------------- database


def _start_pgserver(tmp_root: Path) -> str:
    import pgserver

    server = pgserver.get_server(tmp_root / "pgdata", cleanup_mode="stop")
    server.psql("DROP DATABASE IF EXISTS split_ranch_test;")
    server.psql("CREATE DATABASE split_ranch_test;")
    uri: str = server.get_uri("split_ranch_test")
    return uri


def _migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    engine = create_engine(sqlalchemy_url(url))
    with engine.begin() as conn:
        # The test database is disposable: start from an empty `app` schema.
        conn.execute(text("DROP SCHEMA IF EXISTS app CASCADE"))
    engine.dispose()
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url(url))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    errors: list[str] = []
    if not url:
        try:
            url = _start_pgserver(tmp_path_factory.mktemp("pg"))
        except Exception as exc:  # pragma: no cover - environment specific
            errors.append(f"pgserver: {exc!r}")
    if not url:
        pytest.skip(
            "No PostgreSQL available: set TEST_DATABASE_URL or install pgserver "
            f"({'; '.join(errors)})"
        )
    _migrate(url)
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    eng = create_engine(sqlalchemy_url(database_url), connect_args={"prepare_threshold": None})
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Each test runs inside one outer transaction that is rolled back at the end.

    Use cases' `commit()` only releases a SAVEPOINT. Deferred constraint triggers are
    forced to run before the rollback so share-sum violations still fail the test.
    """
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
        session.close()
        conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    finally:
        trans.rollback()
        conn.close()


# ------------------------------------------------------------------ clock


class FrozenClock:
    def __init__(self) -> None:
        self.value: datetime | None = None

    def set(self, value: datetime) -> None:
        self.value = value if value.tzinfo else value.replace(tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value or datetime.now(UTC)


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> FrozenClock:
    fc = FrozenClock()
    monkeypatch.setattr(clock_module, "utcnow", fc)
    return fc


# ------------------------------------------------------------------- auth


@dataclass
class SigningKey:
    kid: str
    private: ec.EllipticCurvePrivateKey

    @property
    def jwk(self) -> dict[str, Any]:
        data: dict[str, Any] = ECAlgorithm.to_jwk(self.private.public_key(), as_dict=True)
        data.update({"kid": self.kid, "alg": "ES256", "use": "sig"})
        return data


class FakeJWKS:
    """Stands in for PyJWKClient: resolves keys by `kid` from an in-memory JWKS."""

    def __init__(self, keys: list[SigningKey]) -> None:
        self.keys = {k.kid: k for k in keys}

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        kid = jwt.get_unverified_header(token).get("kid")
        key = self.keys.get(kid) if kid else None
        if key is None:
            raise jwt.PyJWKClientError(f'Unable to find a signing key that matches: "{kid}"')
        return jwt.PyJWK.from_dict(key.jwk)


@pytest.fixture(scope="session")
def signing_key() -> SigningKey:
    return SigningKey(KID, ec.generate_private_key(ec.SECP256R1()))


def make_token(
    key: SigningKey,
    sub: uuid.UUID | str,
    *,
    email: str | None = None,
    name: str | None = None,
    iss: str = ISSUER,
    aud: str = "authenticated",
    role: str = "authenticated",
    exp_in: int = 3600,
    kid: str | None = None,
    extra: dict[str, object] | None = None,
) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "sub": str(sub),
        "iss": iss,
        "aud": aud,
        "role": role,
        "iat": now,
        "exp": now + exp_in,
        "email": email or f"{sub}@example.com",
        "user_metadata": {"full_name": name or "Test User"},
        **(extra or {}),
    }
    return jwt.encode(claims, key.private, algorithm="ES256", headers={"kid": kid or key.kid})


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        supabase_url="https://test-project.supabase.co",
        ensure_user_cache_seconds=0,
        # Off by default so long tests never hit them; test_rate_limit turns them on.
        rate_limit_per_minute=0,
        invite_rate_limit_per_minute=0,
        log_json=False,
        log_level="WARNING",
        # apps/api/.env may hold a real DSN; tests must never report to Sentry.
        sentry_dsn=None,
        # apps/api/.env may hold the real secret key: tests never reach Supabase Auth
        # (test_account_deletion injects a fake admin client).
        supabase_secret_key=None,
        # Tests never reach Expo; test_notifications injects its own notifier.
        push_enabled=False,
        expo_access_token=None,
    )


@pytest.fixture
def token_verifier(signing_key: SigningKey) -> TokenVerifier:
    return TokenVerifier(
        jwks_url="https://unused.invalid/jwks.json",
        issuer=ISSUER,
        key_source=FakeJWKS([signing_key]),
    )


@pytest.fixture
def app(
    settings: Settings, engine: Engine, db_session: Session, token_verifier: TokenVerifier
) -> FastAPI:
    application = create_app(settings, engine=engine, token_verifier=token_verifier)

    def _session() -> Iterator[Session]:
        try:
            yield db_session
        finally:
            # Mirrors production: anything a failed request did not commit is discarded.
            db_session.rollback()

    application.dependency_overrides[get_session] = _session
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@dataclass
class TestUser:
    __test__ = False
    id: uuid.UUID
    name: str
    headers: dict[str, str]


@pytest.fixture
def make_user(signing_key: SigningKey) -> Callable[[str], TestUser]:
    def factory(name: str) -> TestUser:
        uid = uuid.uuid4()
        token = make_token(
            signing_key, uid, name=name, email=f"{name.lower()}-{uid.hex[:6]}@example.com"
        )
        return TestUser(uid, name, {"Authorization": f"Bearer {token}"})

    return factory
