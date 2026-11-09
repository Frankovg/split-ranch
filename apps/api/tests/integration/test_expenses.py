"""Expense CRUD: idempotency, client ids, ETag/If-Match, drafts, revisions, list."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from split_ranch.core.ids import uuid7
from tests.conftest import FrozenClock, TestUser
from tests.integration.helpers import House, add_expense, make_house, ok


@pytest.fixture
def house(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> House:
    frozen_clock.set(datetime(2026, 3, 5, tzinfo=UTC))
    return make_house(client, make_user, ("Juli", "Franco", "Ana"))


def _body(house: House, **kw: object) -> dict[str, object]:
    body: dict[str, object] = {
        "amount_cents": 1000,
        "description": "Pan",
        "payer_member_id": house.members["Juli"],
        "expense_date": "2026-03-03",
    }
    body.update(kw)
    return body


def test_strict_input(client: TestClient, house: House) -> None:
    for bad in (
        {"amount_cents": "1000"},
        {"amount_cents": 10.5},
        {"amount_cents": 0},
        {"amount_cents": 100_000_001},
        {"currency": "USD"},
        {"user_id": str(uuid.uuid4())},
        {"split": {"split_type": "thirds"}},
    ):
        r = client.post(house.url("/expenses"), json=_body(house, **bad), headers=house.h("Juli"))
        assert r.status_code == 422, bad


def test_source_restricted_to_manual(client: TestClient, house: House) -> None:
    r = client.post(
        house.url("/expenses"), json=_body(house, source="ai_text"), headers=house.h("Juli")
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_source"
    r = client.post(
        house.url("/expenses"), json=_body(house, source="adjustment"), headers=house.h("Juli")
    )
    assert r.status_code == 422


def test_idempotency_key(client: TestClient, house: House) -> None:
    key = str(uuid.uuid4())
    hdr = house.h("Juli", **{"Idempotency-Key": key})
    first = client.post(house.url("/expenses"), json=_body(house), headers=hdr)
    assert first.status_code == 201
    assert first.headers["ETag"] == '"1"'
    again = client.post(house.url("/expenses"), json=_body(house), headers=hdr)
    assert again.status_code == 201
    assert again.json()["id"] == first.json()["id"]
    r = client.post(house.url("/expenses"), json=_body(house, amount_cents=2000), headers=hdr)
    assert r.status_code == 422 and r.json()["code"] == "idempotency_key_reuse"
    items = ok(client.get(house.url("/expenses"), headers=house.h("Juli")))["items"]
    assert len(items) == 1


def test_client_supplied_id(client: TestClient, house: House) -> None:
    eid = str(uuid7())
    created = ok(
        client.post(house.url("/expenses"), json=_body(house, id=eid), headers=house.h("Juli")), 201
    )
    assert created["id"] == eid
    # Same payload replay (offline retry) -> existing returned.
    assert (
        ok(client.post(house.url("/expenses"), json=_body(house, id=eid), headers=house.h("Juli")))[
            "id"
        ]
        == eid
    )
    r = client.post(
        house.url("/expenses"), json=_body(house, id=eid, amount_cents=5), headers=house.h("Juli")
    )
    assert r.status_code == 409 and r.json()["code"] == "id_conflict"


def test_update_with_if_match(client: TestClient, house: House) -> None:
    e = add_expense(client, house, "Franco", amount=1000, payer="Franco", date="2026-03-03")
    url = house.url(f"/expenses/{e['id']}")
    r = client.patch(url, json={"amount_cents": 1200}, headers=house.h("Franco"))
    assert r.status_code == 428
    r = client.patch(
        url, json={"amount_cents": 1200}, headers=house.h("Franco", **{"If-Match": '"9"'})
    )
    assert r.status_code == 412
    assert r.json()["current"]["version"] == 1 and r.headers["ETag"] == '"1"'
    # Members cannot edit others' expenses; admins can.
    r = client.patch(
        url, json={"amount_cents": 1200}, headers=house.h("Ana", **{"If-Match": '"1"'})
    )
    assert r.status_code == 403
    updated = client.patch(
        url,
        json={"amount_cents": 1200, "description": "Fruta"},
        headers=house.h("Juli", **{"If-Match": '"1"'}),
    )
    assert updated.status_code == 200 and updated.headers["ETag"] == '"2"'
    body = updated.json()
    assert body["version"] == 2 and body["description"] == "Fruta"
    assert [s["amount_cents"] for s in body["shares"]] == [400, 400, 400]
    revs = ok(client.get(f"{url}/revisions", headers=house.h("Ana")))
    assert [r["action"] for r in revs] == ["create", "update"]
    assert revs[1]["before"]["amount_cents"] == 1000 and revs[1]["after"]["amount_cents"] == 1200
    assert revs[1]["after"]["shares"][0]["amount_cents"] == 400

    # A new date does not move the expense to another period.
    moved = ok(
        client.patch(
            url, json={"expense_date": "2026-04-01"}, headers=house.h("Juli", **{"If-Match": '"2"'})
        )
    )
    assert moved["expense_date"] == "2026-04-01" and moved["period"]["seq"] == 1


def test_override_kept_on_amount_change(client: TestClient, house: House) -> None:
    m = house.members
    e = add_expense(
        client,
        house,
        "Juli",
        amount=1000,
        payer="Juli",
        date="2026-03-03",
        split={
            "split_type": "weights",
            "shares": [{"member_id": m["Juli"], "weight": 3}, {"member_id": m["Ana"], "weight": 1}],
        },
    )
    upd = ok(
        client.patch(
            house.url(f"/expenses/{e['id']}"),
            json={"amount_cents": 2000},
            headers=house.h("Juli", **{"If-Match": '"1"'}),
        )
    )
    assert [(s["member_id"], s["amount_cents"]) for s in upd["shares"]] == [
        (m["Juli"], 1500),
        (m["Ana"], 500),
    ]
    assert upd["split_origin"] == "override"


def test_delete_soft(client: TestClient, house: House) -> None:
    e = add_expense(client, house, "Juli", amount=1000, payer="Juli", date="2026-03-03")
    url = house.url(f"/expenses/{e['id']}")
    assert client.delete(url, headers=house.h("Juli")).status_code == 428
    ok(client.delete(url, headers=house.h("Juli", **{"If-Match": '"1"'})), 204)
    got = ok(client.get(url, headers=house.h("Juli")))
    assert got["deleted_at"] is not None and got["can_edit"] is False
    assert ok(client.get(house.url("/expenses"), headers=house.h("Juli")))["items"] == []
    revs = ok(client.get(f"{url}/revisions", headers=house.h("Juli")))
    assert revs[-1]["action"] == "delete"


def test_drafts(client: TestClient, house: House) -> None:
    d = add_expense(
        client, house, "Ana", amount=1000, payer="Ana", date="2026-03-03", status="draft"
    )
    assert d["status"] == "draft"
    assert client.get(house.url(f"/expenses/{d['id']}"), headers=house.h("Juli")).status_code == 404
    assert ok(client.get(house.url("/expenses"), headers=house.h("Juli")))["items"] == []
    assert (
        len(ok(client.get(house.url("/expenses?status=draft"), headers=house.h("Ana")))["items"])
        == 1
    )
    bal = ok(client.get(house.url("/periods/1/balance"), headers=house.h("Ana")))
    assert all(b["net_cents"] == 0 for b in bal["balances"])
    confirmed = ok(
        client.post(
            house.url(f"/expenses/{d['id']}/confirm"), headers=house.h("Ana", **{"If-Match": '"1"'})
        )
    )
    assert confirmed["status"] == "confirmed" and confirmed["version"] == 2
    r = client.post(
        house.url(f"/expenses/{d['id']}/confirm"), headers=house.h("Ana", **{"If-Match": '"2"'})
    )
    assert r.status_code == 409


def test_list_pagination_and_filters(client: TestClient, house: House) -> None:
    for day in range(1, 8):
        add_expense(
            client,
            house,
            "Juli",
            amount=100 * day,
            payer="Juli" if day % 2 else "Franco",
            date=f"2026-03-0{day}",
            description=f"Gasto {day}",
            category="Ocio" if day == 3 else None,
        )
    ok(client.post(house.url("/periods/1/close"), headers=house.h("Juli")))
    ok(client.post(house.url("/periods"), headers=house.h("Juli")), 201)
    add_expense(
        client, house, "Juli", amount=999, payer="Juli", date="2026-04-01", description="Abril"
    )
    seen: list[str] = []
    cursor = None
    while True:
        q = "/expenses?limit=3&period=1" + (f"&cursor={cursor}" if cursor else "")
        page = ok(client.get(house.url(q), headers=house.h("Ana")))
        seen += [i["description"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == [f"Gasto {d}" for d in range(7, 0, -1)]
    by_payer = ok(
        client.get(
            house.url(f"/expenses?payer_member_id={house.members['Franco']}"),
            headers=house.h("Ana"),
        )
    )
    assert len(by_payer["items"]) == 3
    assert (
        len(
            ok(
                client.get(
                    house.url(f"/expenses?category_id={house.categories['Ocio']}"),
                    headers=house.h("Ana"),
                )
            )["items"]
        )
        == 1
    )
    assert len(ok(client.get(house.url("/expenses?q=abr"), headers=house.h("Ana")))["items"]) == 1
    assert client.get(house.url("/expenses?cursor=%%%"), headers=house.h("Ana")).status_code == 422


def test_payer_and_members_validation(
    client: TestClient, house: House, make_user: Callable[[str], TestUser]
) -> None:
    r = client.post(
        house.url("/expenses"),
        json=_body(house, payer_member_id=str(uuid.uuid4())),
        headers=house.h("Juli"),
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_payer"
    r = client.post(
        house.url("/expenses"),
        json=_body(house, participants=[str(uuid.uuid4())]),
        headers=house.h("Juli"),
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_split"
    r = client.post(
        house.url("/expenses"),
        json=_body(
            house,
            split={
                "split_type": "percentages",
                "shares": [{"member_id": house.members["Juli"], "basis_points": 5000}],
            },
        ),
        headers=house.h("Juli"),
    )
    assert r.status_code == 422 and r.json()["code"] == "split_mismatch"


def test_new_expense_in_closed_period(client: TestClient, house: House) -> None:
    add_expense(client, house, "Juli", amount=900, payer="Juli", date="2026-03-03")
    ok(client.post(house.url("/periods/1/close"), headers=house.h("Juli")))
    r = client.post(house.url("/expenses"), json=_body(house), headers=house.h("Franco"))
    assert r.status_code == 409 and r.json()["code"] == "no_open_period"
    r = client.post(
        house.url("/expenses"), json=_body(house, period_seq=1), headers=house.h("Franco")
    )
    assert r.status_code == 409 and r.json()["code"] == "reason_required"
    ok(
        client.post(
            house.url("/expenses"),
            json=_body(house, period_seq=1, reason="Se me olvidó"),
            headers=house.h("Franco"),
        ),
        201,
    )
    settlement = ok(client.get(house.url("/periods/1/settlement"), headers=house.h("Juli")))
    assert settlement["snapshot"]["seq"] == 2
    bal = ok(client.get(house.url("/periods/1/balance"), headers=house.h("Juli")))
    assert bal["drift"] is False
