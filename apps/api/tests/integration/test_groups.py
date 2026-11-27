"""Groups, invitation code, members, categories and split rules."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from split_ranch.use_cases.groups import DEFAULT_CATEGORIES
from tests.conftest import FrozenClock, TestUser
from tests.integration.helpers import add_expense, make_house, nets, ok, pay


def test_create_group_defaults(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    juli = make_user("Juli")
    house = ok(client.post("/v1/groups", json={"name": "Casa Ranch"}, headers=juli.headers), 201)
    assert house["timezone"] == "Europe/Madrid"
    assert house["my_role"] == "admin"
    me = house["members"][0]
    assert me["status"] == "active" and me["joined_at"] and me["left_at"] is None
    cats = ok(client.get(f"/v1/groups/{house['id']}/categories", headers=juli.headers))
    assert [c["name"] for c in cats] == [c[0] for c in DEFAULT_CATEGORIES]
    # No periods any more.
    assert (
        client.get(f"/v1/groups/{house['id']}/periods/current", headers=juli.headers).status_code
        == 404
    )


def test_bad_timezone(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    r = client.post(
        "/v1/groups",
        json={"name": "X", "timezone": "Mars/Base"},
        headers=make_user("A").headers,
    )
    assert r.status_code == 422


def test_several_groups_per_user(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    juli = make_user("Juli")
    ok(client.post("/v1/groups", json={"name": "Piso"}, headers=juli.headers), 201)
    ok(client.post("/v1/groups", json={"name": "Viaje"}, headers=juli.headers), 201)
    names = [g["name"] for g in ok(client.get("/v1/groups", headers=juli.headers))]
    assert names == ["Piso", "Viaje"]
    me = ok(client.get("/v1/me", headers=juli.headers))
    assert [m["group_name"] for m in me["memberships"]] == ["Piso", "Viaje"]


def test_any_member_updates_group(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    house = make_house(client, make_user, ("Juli", "Franco"))
    updated = ok(client.patch(house.url(), json={"name": "Piso"}, headers=house.h("Franco")))
    assert updated["name"] == "Piso"
    r = client.patch(house.url(), json={"grace_days": 5}, headers=house.h("Juli"))
    assert r.status_code == 422


def test_invitation_code(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> None:
    frozen_clock.set(datetime(2026, 3, 20, tzinfo=UTC))
    juli, franco, ana, bea = (
        make_user("Juli"),
        make_user("Franco"),
        make_user("Ana"),
        make_user("Bea"),
    )
    house = ok(client.post("/v1/groups", json={"name": "Casa"}, headers=juli.headers), 201)
    hid = house["id"]
    inv = ok(client.post(f"/v1/groups/{hid}/invitations", headers=juli.headers))
    assert len(inv["code"]) == 8 and set(inv) == {"code", "expires_at"}
    # One code per group: asking again returns the same one while it is valid.
    assert ok(client.post(f"/v1/groups/{hid}/invitations", headers=juli.headers)) == inv

    preview = ok(client.get(f"/v1/invitations/{inv['code']}", headers=franco.headers))
    assert preview == {"group_name": "Casa", "member_count": 1, "expires_at": preview["expires_at"]}
    ok(client.post(f"/v1/invitations/{inv['code']}/accept", headers=franco.headers))
    r = client.post(f"/v1/invitations/{inv['code']}/accept", headers=franco.headers)
    assert r.status_code == 409 and r.json()["code"] == "already_member"
    ok(client.post(f"/v1/invitations/{inv['code'].lower()}/accept", headers=ana.headers))
    # Any member hands out the code (not only the admin).
    assert ok(client.post(f"/v1/groups/{hid}/invitations", headers=franco.headers)) == inv

    # Any member can revoke it; the next invitation gets a new one.
    ok(client.delete(f"/v1/groups/{hid}/invitations", headers=franco.headers), 204)
    assert client.get(f"/v1/invitations/{inv['code']}", headers=bea.headers).status_code == 404
    inv2 = ok(client.post(f"/v1/groups/{hid}/invitations", headers=juli.headers))
    assert inv2["code"] != inv["code"]

    # Codes expire after 7 days.
    frozen_clock.set(datetime(2026, 3, 28, tzinfo=UTC))
    r = client.get(f"/v1/invitations/{inv2['code']}", headers=bea.headers)
    assert r.status_code == 410 and r.json()["code"] == "invitation_expired"
    assert client.get("/v1/invitations/ZZZZZZZZ", headers=bea.headers).status_code == 404
    # A malformed code (here with the NUL byte some clipboards append) is a 404, not a 500.
    r = client.post(f"/v1/invitations/{inv2['code']}%00/accept", headers=bea.headers)
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_joining_never_resplits_existing_expenses(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> None:
    frozen_clock.set(datetime(2026, 3, 5, tzinfo=UTC))
    house = make_house(client, make_user, ("Juli", "Franco"))
    exp = add_expense(client, house, "Juli", amount=900, payer="Juli", date="2026-03-02")
    ana = make_user("Ana")
    inv = ok(client.post(house.url("/invitations"), headers=house.h("Juli")))
    ok(client.post(f"/v1/invitations/{inv['code']}/accept", headers=ana.headers))
    again = ok(client.get(house.url(f"/expenses/{exp['id']}"), headers=house.h("Juli")))
    assert [s["amount_cents"] for s in again["shares"]] == [450, 450]
    # New expenses include the newcomer.
    new = add_expense(client, house, "Juli", amount=900, payer="Juli", date="2026-03-06")
    assert len(new["shares"]) == 3


def test_leaving_needs_zero_balance(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> None:
    frozen_clock.set(datetime(2026, 3, 5, tzinfo=UTC))
    house = make_house(client, make_user, ("Juli", "Franco", "Ana"))
    add_expense(client, house, "Juli", amount=900, payer="Juli", date="2026-03-02")
    r = client.post(house.url("/members/me/leave"), headers=house.h("Ana"))
    assert r.status_code == 409 and r.json()["code"] == "member_has_open_balance"
    assert r.json()["net_cents"] == -300

    # A sent (unconfirmed) payment still blocks leaving.
    p = pay(client, house, "Ana", payer="Ana", to="Juli", amount=300)
    r = client.post(house.url("/members/me/leave"), headers=house.h("Ana"))
    assert r.status_code == 409 and r.json()["pending_payments"] == 1
    ok(
        client.post(
            house.url(f"/payments/{p['id']}/confirm"),
            headers=house.h("Juli", **{"If-Match": '"1"'}),
        )
    )
    ok(client.post(house.url("/members/me/leave"), headers=house.h("Ana")), 204)
    # Former members are not members: 404 like an outsider.
    assert client.get(house.url(), headers=house.h("Ana")).status_code == 404
    group = ok(client.get(house.url(), headers=house.h("Juli")))
    ana = next(m for m in group["members"] if m["id"] == house.members["Ana"])
    assert ana["status"] == "left" and ana["left_at"]
    # Ana's balance stays at zero and still shows.
    assert nets(client, house, "Juli") == {"Juli": 300, "Franco": -300, "Ana": 0}

    # Rejoining reactivates the same member row.
    inv = ok(client.post(house.url("/invitations"), headers=house.h("Juli")))
    back = ok(client.post(f"/v1/invitations/{inv['code']}/accept", headers=house.h("Ana")))
    assert back["my_member_id"] == house.members["Ana"] and back["my_role"] == "member"


def test_admin_rights_and_handover(
    client: TestClient, make_user: Callable[[str], TestUser]
) -> None:
    house = make_house(client, make_user, ("Juli", "Franco", "Ana"))
    # Only the admin removes members; members cannot.
    r = client.delete(house.url(f"/members/{house.members['Ana']}"), headers=house.h("Franco"))
    assert r.status_code == 403
    r = client.delete(house.url(f"/members/{house.members['Juli']}"), headers=house.h("Juli"))
    assert r.status_code == 409 and r.json()["code"] == "cannot_remove_self"
    removed = ok(
        client.delete(house.url(f"/members/{house.members['Ana']}"), headers=house.h("Juli"))
    )
    assert (
        next(m for m in removed["members"] if m["id"] == house.members["Ana"])["status"] == "left"
    )
    # Role changes are gone: the admin role only passes on when the admin leaves.
    r = client.patch(
        house.url(f"/members/{house.members['Franco']}"),
        json={"role": "admin"},
        headers=house.h("Juli"),
    )
    assert r.status_code == 405

    ok(client.post(house.url("/members/me/leave"), headers=house.h("Juli")), 204)
    group = ok(client.get(house.url(), headers=house.h("Franco")))
    assert group["my_role"] == "admin"
    admins = [m for m in group["members"] if m["role"] == "admin"]
    assert [a["id"] for a in admins] == [house.members["Franco"]]

    # The last member leaving deletes the group.
    ok(client.post(house.url("/members/me/leave"), headers=house.h("Franco")), 204)
    assert ok(client.get("/v1/groups", headers=house.h("Franco"))) == []


def test_delete_group(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> None:
    frozen_clock.set(datetime(2026, 3, 5, tzinfo=UTC))
    house = make_house(client, make_user, ("Juli", "Franco"))
    body = {"confirm_name": "Casa"}
    r = client.request("DELETE", house.url(), json=body, headers=house.h("Franco"))
    assert r.status_code == 403
    r = client.request(
        "DELETE", house.url(), json={"confirm_name": "Otra"}, headers=house.h("Juli")
    )
    assert r.status_code == 422 and r.json()["code"] == "confirm_name"
    add_expense(client, house, "Juli", amount=900, payer="Juli", date="2026-03-02")
    r = client.request("DELETE", house.url(), json=body, headers=house.h("Juli"))
    assert r.status_code == 409 and r.json()["code"] == "group_has_open_balances"
    pay(client, house, "Juli", payer="Franco", to="Juli", amount=450)  # cash received
    ok(client.request("DELETE", house.url(), json=body, headers=house.h("Juli")), 204)
    assert client.get(house.url(), headers=house.h("Franco")).status_code == 404
    assert ok(client.get("/v1/groups", headers=house.h("Franco"))) == []


def test_delete_group_waits_for_sent_and_disputed_payments(
    client: TestClient, make_user: Callable[[str], TestUser]
) -> None:
    """C4: a disputed payment can still be confirmed, so it blocks deletion like a sent one."""
    house = make_house(client, make_user, ("Juli", "Franco"))
    body = {"confirm_name": "Casa"}

    def delete() -> Any:
        return client.request("DELETE", house.url(), json=body, headers=house.h("Juli"))

    payment = pay(client, house, "Franco", payer="Franco", to="Juli", amount=100)  # sent
    r = delete()
    assert r.status_code == 409 and r.json()["code"] == "group_has_open_balances"
    ok(
        client.post(
            house.url(f"/payments/{payment['id']}/dispute"),
            json={"note": "No me llegó"},
            headers=house.h("Juli", **{"If-Match": '"1"'}),
        )
    )
    r = delete()
    assert r.status_code == 409 and r.json()["code"] == "group_has_open_balances"
    ok(
        client.post(
            house.url(f"/payments/{payment['id']}/cancel"),
            json={},
            headers=house.h("Franco", **{"If-Match": '"2"'}),
        )
    )
    ok(delete(), 204)


def test_categories_crud(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    house = make_house(client, make_user, ("Juli", "Franco"))
    # Any member manages categories.
    cat = ok(
        client.post(
            house.url("/categories"),
            json={"name": "Mascotas", "color": "#112233"},
            headers=house.h("Franco"),
        ),
        201,
    )
    r = client.post(house.url("/categories"), json={"name": "mascotas"}, headers=house.h("Juli"))
    assert r.status_code == 409 and r.json()["code"] == "category_exists"
    upd = ok(
        client.patch(
            house.url(f"/categories/{cat['id']}"), json={"name": "Perro"}, headers=house.h("Juli")
        )
    )
    assert upd["name"] == "Perro"
    ok(client.delete(house.url(f"/categories/{cat['id']}"), headers=house.h("Franco")), 204)
    names = [c["name"] for c in ok(client.get(house.url("/categories"), headers=house.h("Franco")))]
    assert "Perro" not in names
    archived = ok(
        client.get(house.url("/categories?include_archived=true"), headers=house.h("Franco"))
    )
    assert any(c["name"] == "Perro" and c["archived_at"] for c in archived)
    # Archived categories cannot be used on new expenses.
    r = client.post(
        house.url("/expenses"),
        json={
            "amount_cents": 100,
            "description": "x",
            "payer_member_id": house.members["Juli"],
            "expense_date": "2026-03-01",
            "category_id": cat["id"],
        },
        headers=house.h("Juli"),
    )
    assert r.status_code == 422


def test_rule_precedence_and_fallback(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> None:
    frozen_clock.set(datetime(2026, 3, 5, tzinfo=UTC))
    house = make_house(client, make_user, ("Juli", "Franco", "Ana"))
    m = house.members
    # Default weights 2/1/1, set by a member who is not the admin.
    ok(
        client.put(
            house.url("/split-rules/default"),
            json={
                "split_type": "weights",
                "shares": [
                    {"member_id": m["Juli"], "weight": 2},
                    {"member_id": m["Franco"], "weight": 1},
                    {"member_id": m["Ana"], "weight": 1},
                ],
            },
            headers=house.h("Franco"),
        )
    )
    e = add_expense(
        client, house, "Juli", amount=1001, payer="Juli", date="2026-03-02", category="Healthcare"
    )
    assert [s["amount_cents"] for s in e["shares"]] == [501, 250, 250]
    assert e["split_origin"] == "group_default"
    # Subset with a weights rule keeps the weights of the included members (override).
    e = add_expense(
        client,
        house,
        "Juli",
        amount=900,
        payer="Juli",
        date="2026-03-02",
        participants=[m["Juli"], m["Ana"]],
    )
    assert [s["amount_cents"] for s in e["shares"]] == [600, 300]
    assert e["split_origin"] == "override" and e["participant_mode"] == "subset"

    # A rule change applies only to new expenses (Q1): the Healthcare expense keeps its split.
    ok(
        client.put(
            house.url(f"/categories/{house.categories['Healthcare']}/split-rule"),
            json={"split_type": "equal"},
            headers=house.h("Ana"),
        )
    )
    luz = ok(client.get(house.url("/expenses?q=Healthcare"), headers=house.h("Juli")))["items"][0]
    assert luz["split_origin"] == "group_default"
    assert [s["amount_cents"] for s in luz["shares"]] == [501, 250, 250]
    luz2 = add_expense(
        client, house, "Juli", amount=1001, payer="Juli", date="2026-03-03", category="Healthcare"
    )
    assert luz2["split_origin"] == "category"
    assert [s["amount_cents"] for s in luz2["shares"]] == [334, 334, 333]

    rules = ok(client.get(house.url("/split-rules"), headers=house.h("Franco")))
    assert rules["categories"] == [
        {
            "category_id": house.categories["Healthcare"],
            "split": {"split_type": "equal", "shares": None},
        }
    ]

    # A single rule pointing to a member who left falls back to the next rule.
    ok(
        client.put(
            house.url(f"/categories/{house.categories['Insurance']}/split-rule"),
            json={"split_type": "single", "shares": [{"member_id": m["Ana"]}]},
            headers=house.h("Juli"),
        )
    )
    gas = add_expense(
        client, house, "Juli", amount=400, payer="Juli", date="2026-03-03", category="Insurance"
    )
    assert gas["rule_fallback"] is False and gas["split_origin"] == "category"
    # Settle Ana up (she owes 250 + 300 + 333 + 400) and let her leave.
    owed = -nets(client, house, "Juli")["Ana"]
    pay(client, house, "Juli", payer="Ana", to="Juli", amount=owed)
    ok(client.post(house.url("/members/me/leave"), headers=house.h("Ana")), 204)
    gas2 = add_expense(
        client, house, "Juli", amount=400, payer="Juli", date="2026-03-04", category="Insurance"
    )
    assert gas2["rule_fallback"] is True and gas2["split_origin"] == "group_default"
    assert {s["member_id"] for s in gas2["shares"]} == {m["Juli"], m["Franco"]}

    # Preview does not save.
    preview = ok(
        client.post(
            house.url("/expenses/preview"),
            json={
                "amount_cents": 1000,
                "payer_member_id": m["Juli"],
                "expense_date": "2026-03-04",
                "split": {
                    "split_type": "exact",
                    "shares": [
                        {"member_id": m["Juli"], "amount_cents": 700},
                        {"member_id": m["Franco"], "amount_cents": 300},
                    ],
                },
            },
            headers=house.h("Franco"),
        )
    )
    assert [s["amount_cents"] for s in preview["shares"]] == [700, 300]
    r = client.post(
        house.url("/expenses/preview"),
        json={
            "amount_cents": 1000,
            "payer_member_id": m["Juli"],
            "expense_date": "2026-03-04",
            "split": {
                "split_type": "exact",
                "shares": [{"member_id": m["Juli"], "amount_cents": 700}],
            },
        },
        headers=house.h("Franco"),
    )
    assert r.status_code == 422 and r.json()["code"] == "split_mismatch"


def test_former_admin_cannot_write_anything(
    client: TestClient, make_user: Callable[[str], TestUser]
) -> None:
    """`get_group_actor` is the only membership check: every group write must hit it."""
    house = make_house(client, make_user, ("Juli", "Franco"))
    ok(client.post(house.url("/members/me/leave"), headers=house.h("Juli")), 204)
    juli = house.h("Juli")
    writes = [
        ("PATCH", house.url(), {"name": "Mía"}),
        ("DELETE", house.url(), {"confirm_name": "Casa"}),
        ("POST", house.url("/invitations"), None),
        ("DELETE", house.url(f"/members/{house.members['Franco']}"), None),
        ("POST", house.url("/categories"), {"name": "Gym"}),
        (
            "POST",
            house.url("/expenses"),
            {
                "amount_cents": 900,
                "description": "Cena",
                "payer_member_id": house.members["Juli"],
                "expense_date": "2026-03-02",
            },
        ),
        (
            "POST",
            house.url("/payments"),
            {
                "id": str(uuid.uuid4()),
                "from_member_id": house.members["Juli"],
                "to_member_id": house.members["Franco"],
                "amount_cents": 100,
                "method": "cash",
            },
        ),
    ]
    for method, url, body in writes:
        r = client.request(method, url, json=body, headers=juli)
        assert r.status_code == 404, f"{method} {url}: {r.status_code} {r.text}"
