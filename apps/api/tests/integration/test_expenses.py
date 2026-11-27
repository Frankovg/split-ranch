"""Expense CRUD: client ids (idempotency), ETag/If-Match, revisions, list."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

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
        {"currency": "EUR"},
        {"status": "draft"},
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


def test_client_supplied_id_makes_create_idempotent(client: TestClient, house: House) -> None:
    eid = str(uuid7())
    first = client.post(house.url("/expenses"), json=_body(house, id=eid), headers=house.h("Juli"))
    assert first.status_code == 201 and first.headers["ETag"] == '"1"'
    assert first.json()["id"] == eid
    # Same payload replay (double tap, offline retry) -> the stored expense, no duplicate.
    again = ok(
        client.post(house.url("/expenses"), json=_body(house, id=eid), headers=house.h("Juli"))
    )
    assert again["id"] == eid
    items = ok(client.get(house.url("/expenses"), headers=house.h("Juli")))["items"]
    assert len(items) == 1
    r = client.post(
        house.url("/expenses"), json=_body(house, id=eid, amount_cents=5), headers=house.h("Juli")
    )
    assert r.status_code == 409 and r.json()["code"] == "id_conflict"
    # Another member reusing the id is a conflict too.
    r = client.post(house.url("/expenses"), json=_body(house, id=eid), headers=house.h("Ana"))
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
    # Any member edits any expense (Ana is neither the author nor the admin).
    updated = client.patch(
        url,
        json={"amount_cents": 1200, "description": "Fruta"},
        headers=house.h("Ana", **{"If-Match": '"1"'}),
    )
    assert updated.status_code == 200 and updated.headers["ETag"] == '"2"'
    body = updated.json()
    assert body["version"] == 2 and body["description"] == "Fruta"
    assert [s["amount_cents"] for s in body["shares"]] == [400, 400, 400]
    revs = ok(client.get(f"{url}/revisions", headers=house.h("Ana")))
    assert [r["action"] for r in revs] == ["create", "update"]
    assert revs[1]["before"]["amount_cents"] == 1000 and revs[1]["after"]["amount_cents"] == 1200
    assert revs[1]["after"]["shares"][0]["amount_cents"] == 400

    assert revs[1]["actor_user_id"] == str(house.users["Ana"].id)

    # Only `split`/`participants` re-split: a new category keeps the stored shares (Q1, Q2).
    moved = ok(
        client.patch(
            url,
            json={"expense_date": "2026-04-01", "category_id": house.categories["Entertainment"]},
            headers=house.h("Juli", **{"If-Match": '"2"'}),
        )
    )
    assert moved["expense_date"] == "2026-04-01" and "period" not in moved
    assert [s["amount_cents"] for s in moved["shares"]] == [400, 400, 400]
    resplit = ok(
        client.patch(
            url,
            json={"participants": [house.members["Juli"], house.members["Ana"]]},
            headers=house.h("Juli", **{"If-Match": '"3"'}),
        )
    )
    assert [s["amount_cents"] for s in resplit["shares"]] == [600, 600]


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


def test_list_puts_latest_expense_of_a_day_first(
    client: TestClient, house: House, frozen_clock: FrozenClock
) -> None:
    # Client ids are random, so pick them in the opposite order to creation.
    ids = sorted((uuid.uuid4() for _ in range(3)), reverse=True)
    for n, expense_id in enumerate(ids):
        frozen_clock.set(datetime(2026, 3, 5, 10, n, tzinfo=UTC))
        add_expense(
            client,
            house,
            "Juli",
            amount=100,
            payer="Juli",
            date="2026-03-05",
            description=f"Gasto {n}",
            id=str(expense_id),
        )
    seen: list[str] = []
    cursor = None
    while True:
        q = "/expenses?limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = ok(client.get(house.url(q), headers=house.h("Ana")))
        seen += [i["description"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == ["Gasto 2", "Gasto 1", "Gasto 0"]


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
            category="Entertainment" if day == 3 else None,
        )
    add_expense(
        client, house, "Juli", amount=999, payer="Juli", date="2026-04-01", description="Abril"
    )
    seen: list[str] = []
    cursor = None
    while True:
        # "Last month" is a date range (inclusive).
        q = "/expenses?limit=3&from=2026-03-01&to=2026-03-31" + (
            f"&cursor={cursor}" if cursor else ""
        )
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
                    house.url(f"/expenses?category_id={house.categories['Entertainment']}"),
                    headers=house.h("Ana"),
                )
            )["items"]
        )
        == 1
    )
    assert len(ok(client.get(house.url("/expenses?q=abr"), headers=house.h("Ana")))["items"]) == 1
    assert client.get(house.url("/expenses?cursor=%%%"), headers=house.h("Ana")).status_code == 422
    r = client.get(house.url("/expenses?from=2026-04-01&to=2026-03-01"), headers=house.h("Ana"))
    assert r.status_code == 422
    mine = ok(
        client.get(
            house.url(f"/expenses?created_by_user_id={house.users['Juli'].id}"),
            headers=house.h("Ana"),
        )
    )
    assert len(mine["items"]) == 8


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


def test_period_fields_are_gone(client: TestClient, house: House) -> None:
    for extra in ({"period_seq": 1}, {"reason": "Se me olvidó"}):
        r = client.post(house.url("/expenses"), json=_body(house, **extra), headers=house.h("Juli"))
        assert r.status_code == 422, extra
    assert client.get(house.url("/periods"), headers=house.h("Juli")).status_code == 404


def test_summary_uses_the_list_filters(client: TestClient, house: House) -> None:
    add_expense(
        client,
        house,
        "Juli",
        amount=3000,
        payer="Juli",
        date="2026-03-02",
        category="Entertainment",
    )
    add_expense(client, house, "Juli", amount=1000, payer="Franco", date="2026-03-20")
    add_expense(
        client,
        house,
        "Ana",
        amount=500,
        payer="Ana",
        date="2026-03-21",
        split={"split_type": "personal"},
    )
    add_expense(client, house, "Juli", amount=700, payer="Juli", date="2026-04-01")
    march = ok(
        client.get(house.url("/summary?from=2026-03-01&to=2026-03-31"), headers=house.h("Ana"))
    )
    # The personal expense is not shared spending.
    assert march["count"] == 2 and march["total_cents"] == 4000
    assert march["by_category"] == [
        {"category_id": house.categories["Entertainment"], "total_cents": 3000},
        {"category_id": None, "total_cents": 1000},
    ]
    assert march["by_payer"] == [
        {"member_id": house.members["Juli"], "total_cents": 3000},
        {"member_id": house.members["Franco"], "total_cents": 1000},
    ]
    franco = ok(
        client.get(
            house.url(f"/summary?payer_member_id={house.members['Franco']}"),
            headers=house.h("Ana"),
        )
    )
    assert franco["total_cents"] == 1000


def test_summary_mine_sums_only_my_shares(client: TestClient, house: House) -> None:
    juli, franco = house.members["Juli"], house.members["Franco"]
    add_expense(
        client,
        house,
        "Juli",
        amount=3000,
        payer="Juli",
        date="2026-03-02",
        category="Entertainment",
        participants=[juli, franco],
    )
    # Juli takes no part in this one.
    add_expense(
        client,
        house,
        "Franco",
        amount=1000,
        payer="Franco",
        date="2026-03-03",
        participants=[franco],
    )
    add_expense(
        client,
        house,
        "Juli",
        amount=500,
        payer="Juli",
        date="2026-03-04",
        split={"split_type": "personal"},
    )
    mine = ok(client.get(house.url("/summary?mine=true"), headers=house.h("Juli")))
    # Half of the shared 30.00 plus the whole personal 5.00.
    assert mine["count"] == 2 and mine["total_cents"] == 2000
    assert mine["by_category"] == [
        {"category_id": house.categories["Entertainment"], "total_cents": 1500},
        {"category_id": None, "total_cents": 500},
    ]
    assert mine["by_payer"] == [{"member_id": juli, "total_cents": 2000}]
    # Other filters still apply.
    narrowed = ok(
        client.get(
            house.url(f"/summary?mine=true&category_id={house.categories['Entertainment']}"),
            headers=house.h("Juli"),
        )
    )
    assert narrowed["total_cents"] == 1500
    group = ok(client.get(house.url("/summary"), headers=house.h("Juli")))
    assert group["total_cents"] == 4000


def test_edit_involving_member_who_left_is_refused(client: TestClient, house: House) -> None:
    e = add_expense(
        client,
        house,
        "Juli",
        amount=1000,
        payer="Juli",
        date="2026-03-03",
        participants=[house.members["Juli"], house.members["Franco"]],
    )
    # Settle Franco and let him go: his zero balance must never change again (D2).
    ok(
        client.post(
            house.url("/payments"),
            json={
                "id": str(uuid7()),
                "from_member_id": house.members["Franco"],
                "to_member_id": house.members["Juli"],
                "amount_cents": 500,
                "method": "cash",
            },
            headers=house.h("Juli"),
        ),
        201,
    )
    ok(client.post(house.url("/members/me/leave"), headers=house.h("Franco")), 204)
    r = client.patch(
        house.url(f"/expenses/{e['id']}"),
        json={"amount_cents": 2000},
        headers=house.h("Juli", **{"If-Match": '"1"'}),
    )
    assert r.status_code == 409 and r.json()["code"] == "member_left"
    r = client.post(
        house.url("/expenses"),
        json=_body(house, payer_member_id=house.members["Franco"]),
        headers=house.h("Juli"),
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_payer"


def _count_list_queries(client: TestClient, house: House, db_session: Session) -> int:
    statements: list[str] = []

    def count(*args: object) -> None:
        statements.append(str(args[2]))

    conn = db_session.connection()
    event.listen(conn, "before_cursor_execute", count)
    try:
        ok(client.get(house.url("/expenses?limit=50"), headers=house.h("Ana")))
    finally:
        event.remove(conn, "before_cursor_execute", count)
    return len(statements)


def test_list_loads_shares_in_one_query(
    client: TestClient, house: House, db_session: Session
) -> None:
    """P1: the number of queries does not grow with the page size (no N+1 on shares)."""
    for day in range(1, 3):
        add_expense(client, house, "Juli", amount=300, payer="Juli", date=f"2026-03-0{day}")
    small = _count_list_queries(client, house, db_session)
    for day in range(3, 7):
        add_expense(client, house, "Juli", amount=300, payer="Juli", date=f"2026-03-0{day}")
    page = ok(client.get(house.url("/expenses?limit=50"), headers=house.h("Ana")))
    assert len(page["items"]) == 6
    assert all(len(i["shares"]) == 3 for i in page["items"])
    assert _count_list_queries(client, house, db_session) == small


@pytest.mark.parametrize("path", ["/expenses", "/payments"])
@pytest.mark.parametrize("cursor", ["not-base64!", "e30", "eyJ0IjoxfQ"])
def test_invalid_cursor_is_422(client: TestClient, house: House, path: str, cursor: str) -> None:
    """Garbage, `{}` and `{"t": 1}` are all rejected by the shared cursor decoder."""
    r = client.get(house.url(f"{path}?cursor={cursor}"), headers=house.h("Ana"))
    assert r.status_code == 422, r.text
