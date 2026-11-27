"""DELETE /v1/me: settle-first rule, leaving every group, anonymisation, auth user."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from split_ranch.integrations.supabase_admin import AuthAdminError
from split_ranch.models import Group, PushToken, User
from tests.conftest import TestUser
from tests.integration.helpers import add_expense, make_house, ok, pay

CONFIRM = {"confirm": "DELETE"}


class FakeAuthAdmin:
    def __init__(self, *, fail: bool = False) -> None:
        self.deleted: list[uuid.UUID] = []
        self.fail = fail

    def delete_user(self, user_id: uuid.UUID) -> None:
        if self.fail:
            raise AuthAdminError("boom")
        self.deleted.append(user_id)


def _delete(client: TestClient, user: TestUser) -> httpx.Response:
    return client.request("DELETE", "/v1/me", json=CONFIRM, headers=user.headers)


def test_requires_every_group_settled(
    app: FastAPI, client: TestClient, make_user: Callable[[str], TestUser]
) -> None:
    admin = FakeAuthAdmin()
    app.state.auth_admin = admin
    house = make_house(client, make_user)
    add_expense(client, house, "Franco", amount=300, payer="Franco", date="2026-03-01")

    r = _delete(client, house.users["Juli"])
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "account_has_open_balances"
    assert body["groups"] == [
        {"group_id": house.id, "group_name": "Casa", "net_cents": -100, "pending_payments": 0}
    ]
    # Nothing changed: still a member, auth user untouched.
    assert admin.deleted == []
    assert ok(client.get(house.url(), headers=house.h("Juli")))["my_role"] == "admin"


def test_deletes_and_anonymises(
    app: FastAPI,
    client: TestClient,
    db_session: Session,
    make_user: Callable[[str], TestUser],
) -> None:
    admin = FakeAuthAdmin()
    app.state.auth_admin = admin
    house = make_house(client, make_user)
    juli = house.users["Juli"]
    expense = add_expense(client, house, "Juli", amount=300, payer="Franco", date="2026-03-01")
    # Franco (the receiver) records Juli's payment: confirmed, Juli's net is zero.
    pay(client, house, "Franco", payer="Juli", to="Franco", amount=100)
    solo = ok(client.post("/v1/groups", json={"name": "Solo"}, headers=juli.headers), 201)
    ok(
        client.put(
            "/v1/me/push-tokens",
            json={"token": "ExponentPushToken[juli]", "platform": "android", "locale": "es"},
            headers=juli.headers,
        ),
        204,
    )

    r = client.request("DELETE", "/v1/me", json={"confirm": "yes"}, headers=juli.headers)
    assert r.status_code == 422
    assert _delete(client, juli).status_code == 204
    assert admin.deleted == [juli.id]

    user = db_session.get(User, juli.id)
    assert user is not None and user.deleted_at is not None
    assert (user.email, user.display_name, user.avatar_url) == (None, None, None)
    tokens = db_session.scalar(
        select(func.count()).select_from(PushToken).where(PushToken.user_id == juli.id)
    )
    assert tokens == 0
    # The group where Juli was alone is gone.
    solo_group = db_session.get(Group, uuid.UUID(solo["id"]))
    assert solo_group is not None and solo_group.deleted_at is not None

    # The others keep the records; Juli is a former member and the admin role moved on.
    group = ok(client.get(house.url(), headers=house.h("Franco")))
    assert group["my_role"] == "admin"
    former = next(m for m in group["members"] if m["id"] == house.members["Juli"])
    assert former["status"] == "left"
    assert former["account_deleted"] is True and former["display_name"] is None
    assert all(not m["account_deleted"] for m in group["members"] if m is not former)
    kept = ok(client.get(house.url(f"/expenses/{expense['id']}"), headers=house.h("Ana")))
    assert kept["created_by_user_id"] == str(juli.id)

    # The still-valid token cannot bring the account back.
    r = client.get("/v1/me", headers=juli.headers)
    assert r.status_code == 401 and r.json()["code"] == "account_deleted"
    r = client.post("/v1/groups", json={"name": "Again"}, headers=juli.headers)
    assert r.status_code == 401


def test_auth_failure_changes_nothing(
    app: FastAPI,
    client: TestClient,
    db_session: Session,
    make_user: Callable[[str], TestUser],
) -> None:
    app.state.auth_admin = FakeAuthAdmin(fail=True)
    house = make_house(client, make_user, ("Juli", "Franco"))

    r = _delete(client, house.users["Juli"])
    assert r.status_code == 502
    assert r.json()["code"] == "account_deletion_failed"
    user = db_session.get(User, house.users["Juli"].id)
    assert user is not None and user.deleted_at is None and user.email is not None
    assert ok(client.get(house.url(), headers=house.h("Juli")))["my_role"] == "admin"


def test_unavailable_without_secret_key(
    client: TestClient, make_user: Callable[[str], TestUser]
) -> None:
    r = _delete(client, make_user("Juli"))
    assert r.status_code == 503
    assert r.json()["code"] == "account_deletion_unavailable"
