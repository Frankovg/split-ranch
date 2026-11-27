"""Names and descriptions are trimmed by the schemas: blank input is a 422, never a 500."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import TestUser
from tests.integration.helpers import House, add_expense, make_house, ok, pay

BLANK = " \t \n "


def _expense(client: TestClient, house: House) -> dict[str, Any]:
    body: dict[str, Any] = add_expense(
        client, house, "Juli", amount=900, payer="Juli", date="2026-03-02"
    )
    return body


# (method, path builder, json body) for every write that takes a name or description.
CASES: dict[str, Callable[[TestClient, House], tuple[str, str, dict[str, Any], dict[str, str]]]] = {
    "create group": lambda c, h: ("POST", "/v1/groups", {"name": BLANK}, {}),
    "rename group": lambda c, h: ("PATCH", h.url(), {"name": BLANK}, {}),
    "delete group": lambda c, h: ("DELETE", h.url(), {"confirm_name": BLANK}, {}),
    "create category": lambda c, h: ("POST", h.url("/categories"), {"name": BLANK}, {}),
    "rename category": lambda c, h: (
        "PATCH",
        h.url(f"/categories/{h.categories['Groceries']}"),
        {"name": BLANK},
        {},
    ),
    "create preset": lambda c, h: (
        "POST",
        h.url("/category-presets"),
        {"keyword": BLANK, "category_id": h.categories["Groceries"]},
        {},
    ),
    "create expense": lambda c, h: (
        "POST",
        h.url("/expenses"),
        {
            "amount_cents": 900,
            "description": BLANK,
            "payer_member_id": h.members["Juli"],
            "expense_date": "2026-03-02",
        },
        {},
    ),
    "edit expense": lambda c, h: (
        "PATCH",
        h.url(f"/expenses/{_expense(c, h)['id']}"),
        {"description": BLANK},
        {"If-Match": '"1"'},
    ),
    "rename me": lambda c, h: ("PATCH", "/v1/me", {"display_name": BLANK}, {}),
}


@pytest.mark.parametrize("case", list(CASES))
def test_blank_text_is_rejected(
    client: TestClient, make_user: Callable[[str], TestUser], case: str
) -> None:
    house = make_house(client, make_user, ("Juli", "Franco"))
    method, url, body, extra = CASES[case](client, house)
    r = client.request(method, url, json=body, headers=house.h("Juli", **extra))
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "validation_error"


def test_blank_dispute_note_is_rejected(
    client: TestClient, make_user: Callable[[str], TestUser]
) -> None:
    house = make_house(client, make_user, ("Juli", "Franco"))
    payment = pay(client, house, "Franco", payer="Franco", to="Juli", amount=100)
    r = client.post(
        house.url(f"/payments/{payment['id']}/dispute"),
        json={"note": BLANK},
        headers=house.h("Juli", **{"If-Match": '"1"'}),
    )
    assert r.status_code == 422 and r.json()["code"] == "validation_error"


def test_text_is_stored_trimmed(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    house = make_house(client, make_user, ("Juli", "Franco"))
    renamed = ok(client.patch(house.url(), json={"name": "  Piso "}, headers=house.h("Juli")))
    assert renamed["name"] == "Piso"
    category = ok(
        client.post(house.url("/categories"), json={"name": " Gym "}, headers=house.h("Juli")),
        201,
    )
    assert category["name"] == "Gym"
    expense = add_expense(
        client, house, "Juli", amount=900, payer="Juli", date="2026-03-02", description=" Cena "
    )
    assert expense["description"] == "Cena"
    # Up to the limit after trimming: the padding does not count against max_length.
    long_name = "x" * 80
    renamed = ok(
        client.patch(house.url(), json={"name": f" {long_name} "}, headers=house.h("Juli"))
    )
    assert renamed["name"] == long_name


def test_padded_group_name_can_still_be_deleted(
    client: TestClient, make_user: Callable[[str], TestUser], db_session: Session
) -> None:
    """C3: "Piso " stored before names were trimmed is deleted by confirming "Piso"."""
    house = make_house(client, make_user, ("Juli",))
    ok(client.patch(house.url(), json={"name": "Piso "}, headers=house.h("Juli")))
    db_session.execute(text("UPDATE app.groups SET name = 'Piso ' WHERE id = :g"), {"g": house.id})
    r = client.request(
        "DELETE", house.url(), json={"confirm_name": " Piso"}, headers=house.h("Juli")
    )
    assert r.status_code == 204, r.text
