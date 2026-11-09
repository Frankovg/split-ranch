"""HTTP helpers for integration tests."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import TestUser


@dataclass
class House:
    id: str
    users: dict[str, TestUser]
    members: dict[str, str]  # name -> member_id
    categories: dict[str, str]  # name -> category_id

    def url(self, path: str = "") -> str:
        return f"/v1/households/{self.id}{path}"

    def h(self, name: str, **extra: str) -> dict[str, str]:
        return {**self.users[name].headers, **extra}


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def make_house(
    client: TestClient,
    make_user: Callable[[str], TestUser],
    names: tuple[str, ...] = ("Juli", "Franco", "Ana"),
    *,
    start_period: str = "current",
) -> House:
    users = {n: make_user(n) for n in names}
    admin = users[names[0]]
    house = ok(client.post("/v1/households", json={"name": "Casa"}, headers=admin.headers), 201)
    hid = house["id"]
    for n in names[1:]:
        inv = ok(
            client.post(f"/v1/households/{hid}/invitations", json={}, headers=admin.headers), 201
        )
        ok(
            client.post(
                f"/v1/invitations/{inv['code']}/accept",
                json={"start_period": start_period},
                headers=users[n].headers,
            )
        )
    house = ok(client.get(f"/v1/households/{hid}", headers=admin.headers))
    by_user = {u.id: n for n, u in users.items()}
    members = {by_user[uuid.UUID(m["user_id"])]: m["id"] for m in house["members"]}
    cats = ok(client.get(f"/v1/households/{hid}/categories", headers=admin.headers))
    return House(hid, users, members, {c["name"]: c["id"] for c in cats})


def add_expense(
    client: TestClient,
    house: House,
    who: str,
    *,
    amount: int,
    payer: str,
    date: str,
    category: str | None = None,
    description: str | None = None,
    expect: int = 201,
    **extra: Any,
) -> Any:
    body: dict[str, Any] = {
        "amount_cents": amount,
        "description": description or category or "Gasto",
        "payer_member_id": house.members[payer],
        "expense_date": date,
        **extra,
    }
    if category:
        body["category_id"] = house.categories[category]
    return ok(client.post(house.url("/expenses"), json=body, headers=house.h(who)), expect)


def nets(client: TestClient, house: House, period: str, who: str | None = None) -> dict[str, int]:
    who = who or next(iter(house.users))
    body = ok(client.get(house.url(f"/periods/{period}/balance"), headers=house.h(who)))
    names = {v: k for k, v in house.members.items()}
    return {names[b["member_id"]]: b["net_cents"] for b in body["balances"]}
