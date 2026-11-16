"""Skeleton: health, config, problem+json, auth dependency end to end."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.conftest import SigningKey, TestUser, make_token


def test_healthz_and_config(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/v1/readyz").json() == {"status": "ok"}
    cfg = client.get("/v1/config").json()
    assert "min_app_version" in cfg
    assert client.get("/v1/healthz").headers["X-Min-App-Version"]


def test_missing_token_is_problem_json(client: TestClient) -> None:
    r = client.get("/v1/me")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "unauthenticated"
    assert body["status"] == 401


def test_expired_token_code(client: TestClient, signing_key: SigningKey) -> None:
    token = make_token(signing_key, uuid.uuid4(), exp_in=-600)
    r = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["code"] == "token_expired"


def test_me_creates_user(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    juli = make_user("Juli")
    r = client.get("/v1/me", headers=juli.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == str(juli.id)
    assert body["display_name"] == "Juli"
    assert body["memberships"] == []
    # Idempotent upsert.
    assert client.get("/v1/me", headers=juli.headers).status_code == 200
    r = client.patch("/v1/me", json={"display_name": "Julieta"}, headers=juli.headers)
    assert r.json()["display_name"] == "Julieta"


def test_validation_error_shape(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    u = make_user("Ana")
    r = client.post("/v1/groups", json={"name": "Casa", "extra": 1}, headers=u.headers)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error"
    assert body["errors"]
