"""Every household route returns 404 to a non-member (generated from the OpenAPI paths)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import FrozenClock, TestUser
from tests.integration.helpers import add_expense, make_house, ok


def test_non_member_gets_404_everywhere(
    app: FastAPI,
    client: TestClient,
    make_user: Callable[[str], TestUser],
    frozen_clock: FrozenClock,
) -> None:
    frozen_clock.set(datetime(2026, 3, 5, tzinfo=UTC))
    house = make_house(client, make_user, ("Juli", "Franco"))
    expense = add_expense(client, house, "Juli", amount=1000, payer="Juli", date="2026-03-02")
    ok(client.post(house.url("/periods/1/close"), headers=house.h("Juli")))
    settlement = ok(client.get(house.url("/periods/1/settlement"), headers=house.h("Juli")))
    real_ids = {
        "household_id": house.id,
        "expense_id": expense["id"],
        "member_id": house.members["Franco"],
        "category_id": house.categories["Supermercado"],
        "transfer_id": settlement["transfers"][0]["id"],
        "period": "1",
    }
    outsider = make_user("Mallory")
    # The outsider has a household of their own: membership must be checked per path.
    ok(client.post("/v1/households", json={"name": "Otra"}, headers=outsider.headers), 201)

    checked = 0
    for path, operations in app.openapi()["paths"].items():
        if "{household_id}" not in path:
            continue
        url = path
        for name, value in real_ids.items():
            url = url.replace("{" + name + "}", value)
        assert "{" not in url, f"unmapped path parameter in {path}"
        for method in operations:
            response = client.request(method.upper(), url, headers=outsider.headers, json={})
            assert response.status_code == 404, f"{method.upper()} {path} -> {response.status_code}"
            assert response.json()["code"] == "not_found"
            checked += 1
    assert checked >= 30

    # And the data is intact for real members.
    assert ok(client.get(house.url(f"/expenses/{expense['id']}"), headers=house.h("Franco")))["id"]
