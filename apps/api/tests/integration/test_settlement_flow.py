"""docs/03 worked examples end to end: household March, close, transfers, adjustments."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import FrozenClock, TestUser
from tests.integration.helpers import House, add_expense, make_house, nets, ok


@pytest.fixture
def march_house(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> House:
    frozen_clock.set(datetime(2026, 3, 5, 10, 0, tzinfo=UTC))
    house = make_house(client, make_user)
    m = house.members
    ok(
        client.put(
            house.url(f"/categories/{house.categories['Alquiler']}/split-rule"),
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
            house.url(f"/categories/{house.categories['Internet']}/split-rule"),
            json={"split_type": "single", "shares": [{"member_id": m["Franco"]}]},
            headers=house.h("Juli"),
        )
    )
    return house


def _march_expenses(client: TestClient, house: House) -> dict[str, dict]:
    m = house.members
    e1 = add_expense(
        client, house, "Juli", amount=120000, payer="Juli", date="2026-03-01", category="Alquiler"
    )
    e2 = add_expense(
        client,
        house,
        "Franco",
        amount=10000,
        payer="Franco",
        date="2026-03-02",
        category="Supermercado",
    )
    e3 = add_expense(
        client, house, "Franco", amount=4000, payer="Franco", date="2026-03-03", category="Internet"
    )
    e4 = add_expense(
        client,
        house,
        "Ana",
        amount=6000,
        payer="Ana",
        date="2026-03-04",
        category="Restaurantes",
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


def test_household_example(client: TestClient, march_house: House) -> None:
    house = march_house
    e = _march_expenses(client, house)
    assert _shares(e["E1"], house) == {"Juli": 48000, "Franco": 36000, "Ana": 36000}
    assert e["E1"]["split_origin"] == "category"
    assert _shares(e["E2"], house) == {"Juli": 3334, "Franco": 3333, "Ana": 3333}
    assert e["E2"]["split_origin"] == "household_default"
    assert e["E2"]["participant_mode"] == "all"
    assert _shares(e["E3"], house) == {"Franco": 4000}
    assert _shares(e["E4"], house) == {"Juli": 3000, "Ana": 3000}
    assert e["E4"]["split_origin"] == "override"
    assert e["E5"]["split_type"] == "personal"

    assert nets(client, house, "1") == {"Juli": 65666, "Franco": -29333, "Ana": -36333}

    closed = ok(client.post(house.url("/periods/1/close"), headers=house.h("Juli")))
    assert closed["status"] == "closed"
    settlement = ok(client.get(house.url("/periods/1/settlement"), headers=house.h("Ana")))
    names = {v: k for k, v in house.members.items()}
    transfers = [
        (names[t["from_member_id"]], names[t["to_member_id"]], t["amount_cents"])
        for t in settlement["transfers"]
    ]
    assert transfers == [("Ana", "Juli", 36333), ("Franco", "Juli", 29333)]
    assert settlement["snapshot"]["seq"] == 1
    assert settlement["snapshot"]["trigger"] == "close"
    # Closing again is idempotent.
    assert (
        ok(client.post(house.url("/periods/1/close"), headers=house.h("Juli")))["status"]
        == "closed"
    )


def test_any_member_closes_and_starts_next(client: TestClient, march_house: House) -> None:
    house = march_house
    # A new period can only start once the current one is closed.
    r = client.post(house.url("/periods"), headers=house.h("Ana"))
    assert r.status_code == 409 and r.json()["code"] == "period_open"
    closed = ok(client.post(house.url("/periods/current/close"), headers=house.h("Ana")))
    assert closed["seq"] == 1 and closed["status"] == "settled"  # nothing spent
    # Without an open period, new expenses are refused.
    r = client.post(
        house.url("/expenses"),
        json={
            "amount_cents": 500,
            "description": "Pan",
            "payer_member_id": house.members["Ana"],
            "expense_date": "2026-03-06",
        },
        headers=house.h("Ana"),
    )
    assert r.status_code == 409 and r.json()["code"] == "no_open_period"
    started = ok(client.post(house.url("/periods"), headers=house.h("Franco")), 201)
    assert started["seq"] == 2 and started["status"] == "open"
    current = ok(client.get(house.url("/periods/current"), headers=house.h("Juli")))
    assert current["id"] == started["id"]
    listed = ok(client.get(house.url("/periods"), headers=house.h("Juli")))
    assert [p["seq"] for p in listed["items"]] == [2, 1]
    # Only the latest period can be reopened, and only by an admin.
    r = client.post(
        house.url("/periods/1/reopen"), json={"reason": "Me equivoqué"}, headers=house.h("Juli")
    )
    assert r.status_code == 409 and r.json()["code"] == "period_not_latest"


def _transfer(client: TestClient, house: House, frm: str, period: str = "1") -> dict:
    settlement = ok(client.get(house.url(f"/periods/{period}/settlement"), headers=house.h("Juli")))
    return next(t for t in settlement["transfers"] if t["from_member_id"] == house.members[frm])


def test_adjustment_example(
    client: TestClient, march_house: House, frozen_clock: FrozenClock
) -> None:
    house = march_house
    e = _march_expenses(client, house)
    ok(client.post(house.url("/periods/1/close"), headers=house.h("Juli")))
    t = _transfer(client, house, "Ana")
    ok(
        client.post(
            house.url(f"/transfers/{t['id']}/sent"),
            json={"method": "bizum"},
            headers=house.h("Ana"),
        )
    )

    # March is locked now: in-place edit is refused with an adjustment preview.
    e2 = ok(client.get(house.url(f"/expenses/{e['E2']['id']}"), headers=house.h("Franco")))
    assert e2["edit_mode"] == "adjustment"
    r = client.patch(
        house.url(f"/expenses/{e['E2']['id']}"),
        json={"amount_cents": 13000, "reason": "Era 130 euros"},
        headers=house.h("Franco", **{"If-Match": f'"{e2["version"]}"'}),
    )
    assert r.status_code == 409
    assert r.json()["code"] == "period_locked"
    assert r.json()["adjustment_preview"]["reversal"]["amount_cents"] == -10000

    # Adjustments go to the open period, so somebody starts the next one first.
    r = client.post(
        house.url(f"/expenses/{e['E2']['id']}/adjustments"),
        json={"amount_cents": 13000, "reason": "Era 130 euros"},
        headers=house.h("Franco"),
    )
    assert r.status_code == 409 and r.json()["code"] == "no_open_period"
    frozen_clock.set(datetime(2026, 4, 10, 10, 0, tzinfo=UTC))
    ok(client.post(house.url("/periods"), headers=house.h("Juli")), 201)
    adj = ok(
        client.post(
            house.url(f"/expenses/{e['E2']['id']}/adjustments"),
            json={"amount_cents": 13000, "reason": "Era 130 euros"},
            headers=house.h("Franco"),
        ),
        201,
    )
    assert _shares(adj["reversal"], house) == {"Juli": -3334, "Franco": -3333, "Ana": -3333}
    assert _shares(adj["correction"], house) == {"Juli": 4334, "Franco": 4333, "Ana": 4333}
    assert adj["reversal"]["period"]["seq"] == 2
    assert nets(client, house, "2") == {"Juli": -1000, "Franco": 2000, "Ana": -1000}
    # March snapshot never changes.
    assert nets(client, house, "1") == {"Juli": 65666, "Franco": -29333, "Ana": -36333}


def test_adjustment_delete(
    client: TestClient, march_house: House, frozen_clock: FrozenClock
) -> None:
    house = march_house
    e = _march_expenses(client, house)
    ok(client.post(house.url("/periods/1/close"), headers=house.h("Juli")))
    t = _transfer(client, house, "Franco")
    ok(client.post(house.url(f"/transfers/{t['id']}/confirm"), headers=house.h("Juli")))
    frozen_clock.set(datetime(2026, 4, 2, 10, 0, tzinfo=UTC))
    ok(client.post(house.url("/periods"), headers=house.h("Franco")), 201)
    adj = ok(
        client.post(
            house.url(f"/expenses/{e['E3']['id']}/adjustments"),
            json={"delete": True, "reason": "Duplicado"},
            headers=house.h("Juli"),
        ),
        201,
    )
    assert adj["correction"] is None
    assert nets(client, house, "2") == {"Juli": 0, "Franco": -4000 + 4000, "Ana": 0}


def test_adjustment_requires_locked_period(client: TestClient, march_house: House) -> None:
    house = march_house
    e = _march_expenses(client, house)
    r = client.post(
        house.url(f"/expenses/{e['E2']['id']}/adjustments"),
        json={"amount_cents": 13000, "reason": "Era 130 euros"},
        headers=house.h("Franco"),
    )
    assert r.status_code == 409
    assert r.json()["code"] == "period_not_locked"


def test_transfer_state_machine(client: TestClient, march_house: House) -> None:
    house = march_house
    _march_expenses(client, house)
    ok(client.post(house.url("/periods/1/close"), headers=house.h("Juli")))
    ana_t = _transfer(client, house, "Ana")
    franco_t = _transfer(client, house, "Franco")
    url = lambda t, action: house.url(f"/transfers/{t['id']}/{action}")  # noqa: E731

    # Only the debtor marks sent; only the creditor confirms/disputes.
    assert client.post(url(ana_t, "sent"), headers=house.h("Franco")).status_code == 403
    assert client.post(url(ana_t, "confirm"), headers=house.h("Ana")).status_code == 403
    # Dispute requires `sent`.
    r = client.post(url(ana_t, "dispute"), json={"note": "No"}, headers=house.h("Juli"))
    assert r.status_code == 409 and r.json()["code"] == "invalid_transition"

    assert ok(client.post(url(ana_t, "sent"), headers=house.h("Ana")))["status"] == "sent"
    assert (
        ok(
            client.post(
                url(ana_t, "dispute"), json={"note": "No me llegó"}, headers=house.h("Juli")
            )
        )["status"]
        == "disputed"
    )
    assert ok(client.post(url(ana_t, "sent"), headers=house.h("Ana")))["status"] == "sent"
    assert ok(client.post(url(ana_t, "confirm"), headers=house.h("Juli")))["status"] == "confirmed"
    r = client.post(url(ana_t, "confirm"), headers=house.h("Juli"))
    assert r.status_code == 409

    # Only admins reopen.
    r = client.post(
        house.url("/periods/1/reopen"), json={"reason": "Me equivoqué"}, headers=house.h("Ana")
    )
    assert r.status_code == 403
    # Locked: cannot reopen.
    r = client.post(
        house.url("/periods/1/reopen"),
        json={"reason": "Me equivoqué"},
        headers=house.h("Juli"),
    )
    assert r.status_code == 409 and r.json()["code"] == "period_locked"

    # Cash: the creditor confirms directly from pending. All confirmed -> settled.
    assert (
        ok(client.post(url(franco_t, "confirm"), headers=house.h("Juli")))["status"] == "confirmed"
    )
    period = ok(client.get(house.url("/periods/1"), headers=house.h("Juli")))
    assert period["status"] == "settled"


def test_edit_after_close_and_reopen(client: TestClient, march_house: House) -> None:
    house = march_house
    e = _march_expenses(client, house)
    ok(client.post(house.url("/periods/1/close"), headers=house.h("Juli")))
    e4 = ok(client.get(house.url(f"/expenses/{e['E4']['id']}"), headers=house.h("Ana")))
    assert e4["edit_requires_reason"] is True
    hdr = house.h("Ana", **{"If-Match": f'"{e4["version"]}"'})

    r = client.patch(
        house.url(f"/expenses/{e['E4']['id']}"), json={"amount_cents": 9000}, headers=hdr
    )
    assert r.status_code == 409 and r.json()["code"] == "reason_required"
    updated = ok(
        client.patch(
            house.url(f"/expenses/{e['E4']['id']}"),
            json={"amount_cents": 9000, "reason": "Faltaba el postre"},
            headers=hdr,
        )
    )
    assert _shares(updated, house) == {"Juli": 4500, "Ana": 4500}
    settlement = ok(client.get(house.url("/periods/1/settlement"), headers=house.h("Juli")))
    assert settlement["snapshot"]["seq"] == 2
    assert settlement["snapshot"]["trigger"] == "edit_after_close"
    assert settlement["previous_snapshots"][0]["superseded_at"] is not None
    assert all(t["status"] == "pending" for t in settlement["transfers"])
    # Nets after edit: Juli 65666-1500, Ana -36333+3000-1500... computed by the server.
    n = nets(client, house, "1")
    assert sum(n.values()) == 0
    assert n["Ana"] == -36333 + 1500

    # Reopen (unlocked) and close again -> seq 3 with trigger reopen_close.
    reopened = ok(
        client.post(
            house.url("/periods/1/reopen"),
            json={"reason": "Revisar gastos"},
            headers=house.h("Juli"),
        )
    )
    assert reopened["status"] == "open" and reopened["reopened_count"] == 1
    ok(client.post(house.url("/periods/1/close"), headers=house.h("Juli")))
    settlement = ok(client.get(house.url("/periods/1/settlement"), headers=house.h("Juli")))
    assert settlement["snapshot"]["seq"] == 3
    assert settlement["snapshot"]["trigger"] == "reopen_close"
    cancelled = [t for s in settlement["previous_snapshots"] for t in s["transfers"]]
    assert cancelled  # history keeps the old proposals


def test_period_never_closes_by_itself(
    client: TestClient, march_house: House, frozen_clock: FrozenClock, db_session: Session
) -> None:
    house = march_house
    _march_expenses(client, house)
    # Months go by: the period stays open and expenses keep landing in it.
    frozen_clock.set(datetime(2026, 6, 1, 10, 0, tzinfo=UTC))
    late = add_expense(client, house, "Juli", amount=300, payer="Juli", date="2026-05-31")
    assert late["period"]["seq"] == 1
    period = ok(client.get(house.url("/periods/1"), headers=house.h("Juli")))
    assert period["status"] == "open"
    assert period["started_at"].startswith("2026-03-05T10:00:00")

    ok(client.post(house.url("/periods/1/close"), headers=house.h("Franco")))
    jobs = (
        db_session.execute(text("SELECT task_name FROM app.procrastinate_jobs ORDER BY id"))
        .scalars()
        .all()
    )
    assert "sync_period_tab" in jobs and "notify_period_closed" in jobs


def test_empty_period_closes_to_settled(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> None:
    frozen_clock.set(datetime(2026, 3, 5, tzinfo=UTC))
    house = make_house(client, make_user, ("Juli", "Franco"))
    closed = ok(client.post(house.url("/periods/1/close"), headers=house.h("Juli")))
    assert closed["status"] == "settled"
