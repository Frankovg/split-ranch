"""docs/03 worked example end to end: running balance, suggestions and payments."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FrozenClock, TestUser
from tests.integration.helpers import House, add_expense, make_house, nets, ok, pay


@pytest.fixture
def march_house(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> House:
    frozen_clock.set(datetime(2026, 3, 5, 10, 0, tzinfo=UTC))
    house = make_house(client, make_user)
    m = house.members
    ok(
        client.put(
            house.url(f"/categories/{house.categories['Rent and Services']}/split-rule"),
            json={
                "split_type": "percentages",
                "shares": [
                    {"member_id": m["Juli"], "basis_points": 4000},
                    {"member_id": m["Franco"], "basis_points": 3000},
                    {"member_id": m["Ana"], "basis_points": 3000},
                ],
            },
            headers=house.h("Juli"),
        )
    )
    ok(
        client.put(
            house.url(f"/categories/{house.categories['Home']}/split-rule"),
            json={"split_type": "single", "shares": [{"member_id": m["Franco"]}]},
            headers=house.h("Juli"),
        )
    )
    return house


def _march_expenses(client: TestClient, house: House) -> dict[str, dict]:
    m = house.members
    e1 = add_expense(
        client,
        house,
        "Juli",
        amount=120000,
        payer="Juli",
        date="2026-03-01",
        category="Rent and Services",
    )
    e2 = add_expense(
        client,
        house,
        "Franco",
        amount=10000,
        payer="Franco",
        date="2026-03-02",
        category="Groceries",
    )
    e3 = add_expense(
        client, house, "Franco", amount=4000, payer="Franco", date="2026-03-03", category="Home"
    )
    e4 = add_expense(
        client,
        house,
        "Ana",
        amount=6000,
        payer="Ana",
        date="2026-03-04",
        category="Restaurants and bars",
        description="Cena",
        participants=[m["Juli"], m["Ana"]],
    )
    e5 = add_expense(
        client,
        house,
        "Ana",
        amount=3500,
        payer="Ana",
        date="2026-03-04",
        description="Gimnasio",
        split={"split_type": "personal"},
    )
    return {"E1": e1, "E2": e2, "E3": e3, "E4": e4, "E5": e5}


def _shares(expense: dict, house: House) -> dict[str, int]:
    names = {v: k for k, v in house.members.items()}
    return {names[s["member_id"]]: s["amount_cents"] for s in expense["shares"]}


def _names(house: House) -> dict[str, str]:
    return {v: k for k, v in house.members.items()}


def _balance(client: TestClient, house: House, who: str = "Juli") -> dict:
    return ok(client.get(house.url("/balance"), headers=house.h(who)))


def _suggestions(client: TestClient, house: House) -> list[tuple[str, str, int]]:
    names = _names(house)
    return [
        (names[s["from_member_id"]], names[s["to_member_id"]], s["amount_cents"])
        for s in _balance(client, house)["suggestions"]
    ]


def _if(who: str, house: House, version: int) -> dict[str, str]:
    return house.h(who, **{"If-Match": f'"{version}"'})


def test_group_example(client: TestClient, march_house: House) -> None:
    house = march_house
    e = _march_expenses(client, house)
    assert _shares(e["E1"], house) == {"Juli": 48000, "Franco": 36000, "Ana": 36000}
    assert e["E1"]["split_origin"] == "category"
    assert _shares(e["E2"], house) == {"Juli": 3334, "Franco": 3333, "Ana": 3333}
    assert e["E2"]["split_origin"] == "group_default"
    assert e["E2"]["participant_mode"] == "all"
    assert _shares(e["E3"], house) == {"Franco": 4000}
    assert _shares(e["E4"], house) == {"Juli": 3000, "Ana": 3000}
    assert e["E4"]["split_origin"] == "override"
    assert e["E5"]["split_type"] == "personal"

    # The personal expense is excluded; the nets sum to 0.
    assert nets(client, house) == {"Juli": 65666, "Franco": -29333, "Ana": -36333}
    assert _suggestions(client, house) == [("Ana", "Juli", 36333), ("Franco", "Juli", 29333)]


def test_payment_flow(client: TestClient, march_house: House) -> None:
    house = march_house
    _march_expenses(client, house)

    # CUJ 4: Franco records "sent"; the balance waits for Juli, the suggestion disappears.
    p = pay(client, house, "Franco", payer="Franco", to="Juli", amount=29333, note="Bizum")
    assert p["status"] == "sent" and p["version"] == 1 and p["method"] == "bizum"
    assert nets(client, house)["Franco"] == -29333
    franco = next(
        b for b in _balance(client, house)["balances"] if b["member_id"] == house.members["Franco"]
    )
    assert franco["pending_out_cents"] == 29333
    assert _suggestions(client, house) == [("Ana", "Juli", 36333)]

    # Only the receiver confirms, with If-Match.
    url = house.url(f"/payments/{p['id']}/confirm")
    assert client.post(url, headers=_if("Franco", house, 1)).status_code == 403
    assert client.post(url, headers=house.h("Juli")).status_code == 428
    assert client.post(url, headers=_if("Juli", house, 7)).status_code == 412
    done = ok(client.post(url, headers=_if("Juli", house, 1)))
    assert done["status"] == "confirmed"
    assert done["confirmed_by_user_id"] == str(house.users["Juli"].id)
    assert nets(client, house) == {"Juli": 36333, "Franco": 0, "Ana": -36333}

    # A confirmed payment cannot change state again.
    r = client.post(house.url(f"/payments/{p['id']}/cancel"), headers=_if("Franco", house, 2))
    assert r.status_code == 409 and r.json()["code"] == "payment_state_changed"

    # CUJ 5: dispute, then the payer cancels and records again.
    p2 = pay(client, house, "Ana", payer="Ana", to="Juli", amount=36333)
    dispute = house.url(f"/payments/{p2['id']}/dispute")
    assert client.post(dispute, json={}, headers=_if("Juli", house, 1)).status_code == 422
    disputed = ok(client.post(dispute, json={"note": "No me llegó"}, headers=_if("Juli", house, 1)))
    assert disputed["status"] == "disputed"
    assert _suggestions(client, house) == [("Ana", "Juli", 36333)]
    ok(client.post(house.url(f"/payments/{p2['id']}/cancel"), headers=_if("Ana", house, 2)))
    # The receiver records cash received directly as confirmed.
    cash = pay(client, house, "Juli", payer="Ana", to="Juli", amount=36333, method="cash")
    assert cash["status"] == "confirmed" and cash["method"] == "cash"
    assert nets(client, house) == {"Juli": 0, "Franco": 0, "Ana": 0}
    assert _suggestions(client, house) == []

    listed = ok(client.get(house.url("/payments?status=cancelled"), headers=house.h("Franco")))
    assert [x["id"] for x in listed["items"]] == [p2["id"]]
    every = ok(client.get(house.url("/payments"), headers=house.h("Franco")))["items"]
    assert {x["id"] for x in every} == {cash["id"], p2["id"], p["id"]}


def test_payment_rules(client: TestClient, march_house: House) -> None:
    house = march_house
    m = house.members
    # A third member cannot record someone else's payment.
    r = client.post(
        house.url("/payments"),
        json={
            "id": "0193a7c2-0000-7000-8000-00000000aaaa",
            "from_member_id": m["Franco"],
            "to_member_id": m["Juli"],
            "amount_cents": 100,
            "method": "cash",
        },
        headers=house.h("Ana"),
    )
    assert r.status_code == 403
    r = client.post(
        house.url("/payments"),
        json={
            "id": "0193a7c2-0000-7000-8000-00000000aaab",
            "from_member_id": m["Ana"],
            "to_member_id": m["Ana"],
            "amount_cents": 100,
            "method": "cash",
        },
        headers=house.h("Ana"),
    )
    assert r.status_code == 422
    # The method is required and must be one of the known ones.
    pay(client, house, "Ana", payer="Ana", to="Juli", amount=100, method=None, expect=422)
    pay(client, house, "Ana", payer="Ana", to="Juli", amount=100, method="paypal", expect=422)

    # Idempotent create: same id and payload -> 200; different payload -> 409.
    body = {
        "id": "0193a7c2-0000-7000-8000-00000000aaac",
        "from_member_id": m["Ana"],
        "to_member_id": m["Juli"],
        "amount_cents": 500,
        "method": "bank_transfer",
    }
    first = ok(client.post(house.url("/payments"), json=body, headers=house.h("Ana")), 201)
    again = ok(client.post(house.url("/payments"), json=body, headers=house.h("Ana")), 200)
    assert again == first
    r = client.post(
        house.url("/payments"), json={**body, "amount_cents": 501}, headers=house.h("Ana")
    )
    assert r.status_code == 409 and r.json()["code"] == "id_conflict"
    r = client.post(house.url("/payments"), json={**body, "method": "cash"}, headers=house.h("Ana"))
    assert r.status_code == 409 and r.json()["code"] == "id_conflict"


def test_editing_old_expense_moves_balance(client: TestClient, march_house: House) -> None:
    house = march_house
    e = _march_expenses(client, house)
    pay(client, house, "Juli", payer="Franco", to="Juli", amount=29333)
    assert nets(client, house)["Franco"] == 0
    # CUJ 6: Groceries was 130,00 €, not 100,00 €. Any member fixes it in place; the
    # equal split over the same members is re-allocated.
    updated = ok(
        client.patch(
            house.url(f"/expenses/{e['E2']['id']}"),
            json={"amount_cents": 13000},
            headers=_if("Ana", house, 1),
        )
    )
    assert _shares(updated, house) == {"Juli": 4334, "Franco": 4333, "Ana": 4333}
    assert updated["split_origin"] == "group_default"
    assert updated["updated_by_user_id"] == str(house.users["Ana"].id)
    # Franco paid 30,00 € more and owes 10,00 € more: +20,00 €.
    assert nets(client, house) == {"Juli": 35333, "Franco": 2000, "Ana": -37333}
