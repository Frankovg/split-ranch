"""The per-request access log line carries the (hashed) user and the group."""

from __future__ import annotations

from collections.abc import Callable

import pytest
import structlog
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from split_ranch import main
from split_ranch.core.logging import hash_user_id
from split_ranch.core.settings import Settings
from tests.conftest import TestUser
from tests.integration.helpers import ok


@pytest.fixture
def settings(settings: Settings) -> Settings:
    # The access log is emitted at INFO; the shared test settings only keep warnings.
    return settings.model_copy(update={"log_level": "INFO"})


@pytest.fixture(autouse=True)
def fresh_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    # Loggers are cached on first use: an earlier test may have cached the WARNING-level one.
    monkeypatch.setattr(main, "log", structlog.get_logger("split_ranch.main"))


def _request_logs(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    return [e for e in entries if e.get("event") == "request"]


def test_request_log_has_user_and_group(
    client: TestClient, make_user: Callable[[str], TestUser]
) -> None:
    ana = make_user("Ana")
    group = ok(client.post("/v1/groups", json={"name": "Flat"}, headers=ana.headers), 201)
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as entries:
        client.get(f"/v1/groups/{group['id']}", headers=ana.headers)
    [entry] = _request_logs(entries)
    assert entry["status"] == 200
    assert entry["user"] == hash_user_id(ana.id)
    assert entry["group_id"] == group["id"]


def test_request_log_without_auth_has_no_user(client: TestClient) -> None:
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as entries:
        client.get("/v1/groups")
    [entry] = _request_logs(entries)
    assert entry["status"] == 401
    assert "user" not in entry
