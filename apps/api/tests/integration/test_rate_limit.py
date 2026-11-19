"""Per-user rate limits on the API (429 problem+json with Retry-After)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from split_ranch.core.settings import Settings
from tests.conftest import TestUser


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"rate_limit_per_minute": 3, "invite_rate_limit_per_minute": 2}
    )


def test_user_limit_returns_429_with_retry_after(
    client: TestClient, make_user: Callable[[str], TestUser]
) -> None:
    ana = make_user("Ana")
    for _ in range(3):
        assert client.get("/v1/groups", headers=ana.headers).status_code == 200
    res = client.get("/v1/groups", headers=ana.headers)
    assert res.status_code == 429
    assert res.headers["Retry-After"] == "20"
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["code"] == "rate_limited"


def test_user_limit_is_per_user(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    ana, bob = make_user("Ana"), make_user("Bob")
    for _ in range(3):
        client.get("/v1/groups", headers=ana.headers)
    assert client.get("/v1/groups", headers=ana.headers).status_code == 429
    assert client.get("/v1/groups", headers=bob.headers).status_code == 200


def test_invitation_code_guessing_is_limited(
    client: TestClient, make_user: Callable[[str], TestUser]
) -> None:
    eve = make_user("Eve")
    statuses = [
        client.get(f"/v1/invitations/GUESS00{i}", headers=eve.headers).status_code for i in range(3)
    ]
    # Unknown codes fail normally until the invite limit (2/min) kicks in, well below
    # the general limit (3/min).
    assert 429 not in statuses[:2]
    assert statuses[2] == 429
