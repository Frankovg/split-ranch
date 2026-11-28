"""Skeleton: health, config, problem+json, auth dependency end to end."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from split_ranch.core.security import TokenVerifier
from split_ranch.core.settings import Settings
from split_ranch.integrations.expo_push import ExpoPushClient
from split_ranch.main import create_app
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


class _UnreachableJWKS:
    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        raise jwt.PyJWKClientConnectionError("Fail to fetch data from the url")


def test_unreachable_jwks_is_503_not_401(
    app: FastAPI, client: TestClient, make_user: Callable[[str], TestUser]
) -> None:
    """S1: a Supabase Auth outage must not look like a bad token (the app would refresh)."""
    app.state.token_verifier.key_source = _UnreachableJWKS()
    r = client.get("/v1/me", headers=make_user("Juli").headers)
    assert r.status_code == 503
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.headers["Retry-After"] == "30"
    assert r.json()["code"] == "auth_unavailable"


def test_valid_request_id_is_echoed(client: TestClient) -> None:
    rid = "0f8b2c3e-app-retry-1"
    assert client.get("/healthz", headers={"X-Request-ID": rid}).headers["X-Request-ID"] == rid


@pytest.mark.parametrize(
    "rid",
    ["x" * 65, "abc def", "a_b.c", "<script>", "a;b", ""],
)
def test_invalid_request_id_is_replaced(client: TestClient, rid: str) -> None:
    """S3: an unusual id is never echoed into the response, the logs or Sentry."""
    echoed = client.get("/healthz", headers={"X-Request-ID": rid}).headers["X-Request-ID"]
    assert echoed != rid
    assert len(echoed) == 32 and echoed.isalnum()


def test_config_reports_the_push_setting(
    settings: Settings, engine: Engine, token_verifier: TokenVerifier
) -> None:
    """B4: `features.push` follows `push_enabled` instead of a fixed false."""
    push_client = ExpoPushClient()
    try:
        for enabled in (False, True):
            app = create_app(
                settings.model_copy(update={"push_enabled": enabled}),
                engine=engine,
                token_verifier=token_verifier,
                push_client=push_client,
            )
            features = TestClient(app).get("/v1/config").json()["features"]
            assert features == {"sheets": False, "push": enabled}
    finally:
        push_client.close()


def test_prod_serves_no_schema_or_docs(
    settings: Settings, engine: Engine, token_verifier: TokenVerifier
) -> None:
    """S5: in prod the OpenAPI schema and the docs are not public; the export still works."""
    prod = create_app(
        settings.model_copy(update={"app_env": "prod"}),
        engine=engine,
        token_verifier=token_verifier,
    )
    client = TestClient(prod)
    assert client.get("/v1/openapi.json").status_code == 404
    assert client.get("/v1/docs").status_code == 404
    assert "/v1/groups" in prod.openapi()["paths"]


def test_non_prod_serves_the_schema(client: TestClient) -> None:
    assert client.get("/v1/openapi.json").status_code == 200
