from __future__ import annotations

from typing import Any

import pytest

from split_ranch.core import observability
from split_ranch.core.settings import Settings

FAKE_DSN = "https://public@o0.ingest.de.sentry.io/0"


@pytest.fixture
def init_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(observability.sentry_sdk, "init", lambda **kw: calls.append(kw))
    return calls


def test_sentry_disabled_without_dsn(init_calls: list[dict[str, Any]]) -> None:
    assert observability.init_sentry(Settings(sentry_dsn=None)) is False
    assert init_calls == []


def test_sentry_init_options(init_calls: list[dict[str, Any]]) -> None:
    settings = Settings(app_env="prod", sentry_dsn=FAKE_DSN, SENTRY_RELEASE="abc123")

    assert observability.init_sentry(settings) is True
    assert init_calls == [
        {
            "dsn": FAKE_DSN,
            "environment": "prod",
            "release": "abc123",
            "send_default_pii": False,
            "traces_sample_rate": 0.0,
        }
    ]


def test_release_falls_back_to_render_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_RELEASE", raising=False)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "deadbeef")
    assert Settings().sentry_release == "deadbeef"
