"""B3: on shutdown the app closes what it created, and leaves injected objects alone."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from split_ranch import main
from split_ranch.core.security import TokenVerifier
from split_ranch.core.settings import Settings
from split_ranch.integrations.expo_push import ExpoPushClient
from tests.conftest import ISSUER, FakeJWKS, SigningKey


def _settings() -> Settings:
    return Settings(
        app_env="test",
        supabase_url="https://test-project.supabase.co",
        sentry_dsn=None,
        supabase_secret_key=None,
        push_enabled=True,
        log_json=False,
        log_level="WARNING",
    )


def _verifier(signing_key: SigningKey) -> TokenVerifier:
    return TokenVerifier(
        jwks_url="https://unused.invalid", issuer=ISSUER, key_source=FakeJWKS([signing_key])
    )


class Tracked:
    """Records which resources were closed (an engine and an Expo client never connected)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.closed: list[str] = []
        self.engine = create_engine("postgresql+psycopg://unused@localhost:1/unused")
        self.push = ExpoPushClient()
        monkeypatch.setattr(self.engine, "dispose", lambda: self.closed.append("engine"))
        monkeypatch.setattr(self.push, "close", lambda: self.closed.append("push"))


def test_owned_engine_and_push_client_are_closed(
    monkeypatch: pytest.MonkeyPatch, signing_key: SigningKey
) -> None:
    owned = Tracked(monkeypatch)
    monkeypatch.setattr(main, "create_db_engine", lambda _settings: owned.engine)
    monkeypatch.setattr(main, "ExpoPushClient", lambda **_kwargs: owned.push)
    app = main.create_app(_settings(), token_verifier=_verifier(signing_key))
    with TestClient(app):
        assert owned.closed == []
    assert sorted(owned.closed) == ["engine", "push"]


def test_injected_engine_and_push_client_are_left_open(
    monkeypatch: pytest.MonkeyPatch, signing_key: SigningKey
) -> None:
    injected = Tracked(monkeypatch)
    app = main.create_app(
        _settings(),
        engine=injected.engine,
        push_client=injected.push,
        token_verifier=_verifier(signing_key),
    )
    with TestClient(app):
        pass
    assert injected.closed == []


def test_a_failing_close_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch, signing_key: SigningKey
) -> None:
    owned = Tracked(monkeypatch)

    def broken_dispose() -> None:
        raise RuntimeError("pool already gone")

    monkeypatch.setattr(owned.engine, "dispose", broken_dispose)
    monkeypatch.setattr(main, "create_db_engine", lambda _settings: owned.engine)
    monkeypatch.setattr(main, "ExpoPushClient", lambda **_kwargs: owned.push)
    app = main.create_app(_settings(), token_verifier=_verifier(signing_key))
    with TestClient(app):
        pass
    assert owned.closed == ["push"]
