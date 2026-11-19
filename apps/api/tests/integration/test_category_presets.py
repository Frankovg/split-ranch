"""Category presets: keywords that pick a category for new expenses (per group)."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from split_ranch.models import History
from tests.conftest import TestUser
from tests.integration.helpers import make_house, ok


def test_presets_crud(
    client: TestClient, make_user: Callable[[str], TestUser], db_session: Session
) -> None:
    house = make_house(client, make_user, ("Juli", "Franco"))
    # Empty by default: every group sets its own.
    assert ok(client.get(house.url("/category-presets"), headers=house.h("Juli"))) == []

    groceries = house.categories["Groceries"]
    preset = ok(
        client.post(
            house.url("/category-presets"),
            json={"keyword": "  Supermercado ", "category_id": groceries},
            headers=house.h("Franco"),
        ),
        201,
    )
    assert preset["keyword"] == "Supermercado" and preset["category_id"] == groceries
    ok(
        client.post(
            house.url("/category-presets"),
            json={"keyword": "Gasolina", "category_id": house.categories["Transport"]},
            headers=house.h("Juli"),
        ),
        201,
    )

    # Keywords are unique per group, case ignored.
    r = client.post(
        house.url("/category-presets"),
        json={"keyword": "supermercado", "category_id": house.categories["Shopping"]},
        headers=house.h("Juli"),
    )
    assert r.status_code == 409 and r.json()["code"] == "preset_exists"

    listed = ok(client.get(house.url("/category-presets"), headers=house.h("Juli")))
    assert [p["keyword"] for p in listed] == ["Gasolina", "Supermercado"]

    ok(client.delete(house.url(f"/category-presets/{preset['id']}"), headers=house.h("Juli")), 204)
    listed = ok(client.get(house.url("/category-presets"), headers=house.h("Juli")))
    assert [p["keyword"] for p in listed] == ["Gasolina"]
    r = client.delete(house.url(f"/category-presets/{preset['id']}"), headers=house.h("Juli"))
    assert r.status_code == 404

    # Every change is recorded in history.
    actions = db_session.scalars(
        select(History.action)
        .where(History.group_id == uuid.UUID(house.id), History.entity == "category_preset")
        .order_by(History.created_at, History.id)
    ).all()
    assert sorted(actions) == ["create", "create", "delete"]


def test_preset_validation(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    house = make_house(client, make_user, ("Juli",))
    other = make_house(client, make_user, ("Ana",))
    url = house.url("/category-presets")

    # Blank keyword.
    r = client.post(
        url,
        json={"keyword": "   ", "category_id": house.categories["Groceries"]},
        headers=house.h("Juli"),
    )
    assert r.status_code == 422
    # A category of another group is not one of this group's.
    r = client.post(
        url,
        json={"keyword": "Super", "category_id": other.categories["Groceries"]},
        headers=house.h("Juli"),
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_category"
    # Outsiders get 404.
    assert client.get(url, headers=other.h("Ana")).status_code == 404


def test_archiving_a_category_drops_its_presets(
    client: TestClient, make_user: Callable[[str], TestUser]
) -> None:
    house = make_house(client, make_user, ("Juli",))
    cat = ok(
        client.post(house.url("/categories"), json={"name": "Mascotas"}, headers=house.h("Juli")),
        201,
    )
    url = house.url("/category-presets")
    ok(
        client.post(
            url, json={"keyword": "Pienso", "category_id": cat["id"]}, headers=house.h("Juli")
        ),
        201,
    )
    ok(client.delete(house.url(f"/categories/{cat['id']}"), headers=house.h("Juli")), 204)
    assert ok(client.get(url, headers=house.h("Juli"))) == []
    # The keyword is free again, and archived categories cannot be chosen.
    r = client.post(
        url, json={"keyword": "Pienso", "category_id": cat["id"]}, headers=house.h("Juli")
    )
    assert r.status_code == 422
    ok(
        client.post(
            url,
            json={"keyword": "Pienso", "category_id": house.categories["Shopping"]},
            headers=house.h("Juli"),
        ),
        201,
    )
