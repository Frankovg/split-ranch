"""Households, invitation code, members, categories and split rules."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from split_ranch.use_cases.households import DEFAULT_CATEGORIES
from tests.conftest import FrozenClock, TestUser
from tests.integration.helpers import add_expense, make_house, nets, ok


def test_create_household_defaults(
    client: TestClient, make_user: Callable[[str], TestUser]
) -> None:
    juli = make_user("Juli")
    house = ok(
        client.post("/v1/households", json={"name": "Casa Ranch"}, headers=juli.headers), 201
    )
    assert house["timezone"] == "Europe/Madrid"
    assert "grace_days" not in house and "auto_close" not in house
    assert house["my_role"] == "admin"
    assert house["members"][0]["joined_period_seq"] == 1
    # A new household starts with period 1 open.
    period = ok(client.get(f"/v1/households/{house['id']}/periods/current", headers=juli.headers))
    assert period["seq"] == 1 and period["status"] == "open"
    cats = ok(client.get(f"/v1/households/{house['id']}/categories", headers=juli.headers))
    assert [c["name"] for c in cats] == [c[0] for c in DEFAULT_CATEGORIES]
    assert "Supermercado" in [c["name"] for c in cats]
    rules = ok(client.get(f"/v1/households/{house['id']}/split-rules", headers=juli.headers))
    assert rules["default"]["split_type"] == "equal"
    assert not rules["default"].get("shares")
    assert rules["categories"] == []
    assert "currency" not in house and "version" not in house
    me = ok(client.get("/v1/me", headers=juli.headers))
    assert me["memberships"][0]["role"] == "admin"


def test_bad_timezone(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    r = client.post(
        "/v1/households",
        json={"name": "X", "timezone": "Mars/Base"},
        headers=make_user("A").headers,
    )
    assert r.status_code == 422


def test_household_update(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    house = make_house(client, make_user, ("Juli", "Franco"))
    updated = ok(client.patch(house.url(), json={"name": "Piso"}, headers=house.h("Juli")))
    assert updated["name"] == "Piso"
    r = client.patch(house.url(), json={"name": "Casa"}, headers=house.h("Franco"))
    assert r.status_code == 403
    # Auto-close settings are gone.
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
    house = ok(client.post("/v1/households", json={"name": "Casa"}, headers=juli.headers), 201)
    hid = house["id"]
    inv = ok(client.post(f"/v1/households/{hid}/invitations", headers=juli.headers))
    assert len(inv["code"]) == 8 and inv["url"].endswith(inv["code"])
    # One code per household: asking again returns the same one while it is valid.
    assert ok(client.post(f"/v1/households/{hid}/invitations", headers=juli.headers)) == inv

    preview = ok(client.get(f"/v1/invitations/{inv['code']}", headers=franco.headers))
    assert preview == {
        "household_name": "Casa",
        "member_count": 1,
        "expires_at": preview["expires_at"],
    }
    # A new member joins the open period, whatever the date; the code works for several.
    joined = ok(client.post(f"/v1/invitations/{inv['code']}/accept", headers=franco.headers))
    franco_member = next(m for m in joined["members"] if m["user_id"] == str(franco.id))
    assert franco_member["joined_period_seq"] == 1
    r = client.post(f"/v1/invitations/{inv['code']}/accept", headers=franco.headers)
    assert r.status_code == 409 and r.json()["code"] == "already_member"
    ok(client.post(f"/v1/invitations/{inv['code'].lower()}/accept", headers=ana.headers))
    # Only admins hand out the code.
    r = client.post(f"/v1/households/{hid}/invitations", headers=franco.headers)
    assert r.status_code == 403

    # Revoking invalidates the code; the next invitation gets a new one.
    ok(client.delete(f"/v1/households/{hid}/invitations", headers=juli.headers), 204)
    r = client.get(f"/v1/invitations/{inv['code']}", headers=bea.headers)
    assert r.status_code == 404
    inv2 = ok(client.post(f"/v1/households/{hid}/invitations", headers=juli.headers))
    assert inv2["code"] != inv["code"]

    # Codes expire after 7 days.
    frozen_clock.set(datetime(2026, 3, 28, tzinfo=UTC))
    r = client.get(f"/v1/invitations/{inv2['code']}", headers=bea.headers)
    assert r.status_code == 410 and r.json()["code"] == "invitation_expired"
    inv3 = ok(client.post(f"/v1/households/{hid}/invitations", headers=juli.headers))
    assert inv3["code"] != inv2["code"]
    assert client.get("/v1/invitations/ZZZZZZZZ", headers=bea.headers).status_code == 404


def test_member_joining_current_period_is_included(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> None:
    frozen_clock.set(datetime(2026, 3, 5, tzinfo=UTC))
    house = make_house(client, make_user, ("Juli", "Franco"))
    exp = add_expense(client, house, "Juli", amount=900, payer="Juli", date="2026-03-02")
    assert len(exp["shares"]) == 2
    ana = make_user("Ana")
    inv = ok(client.post(house.url("/invitations"), headers=house.h("Juli")))
    joined = ok(client.post(f"/v1/invitations/{inv['code']}/accept", headers=ana.headers))
    ana_id = next(m["id"] for m in joined["members"] if m["user_id"] == str(ana.id))
    exp = ok(client.get(house.url(f"/expenses/{exp['id']}"), headers=house.h("Juli")))
    assert [s["amount_cents"] for s in exp["shares"]] == [300, 300, 300]
    assert exp["shares"][2]["member_id"] == ana_id
    revisions = ok(
        client.get(house.url(f"/expenses/{exp['id']}/revisions"), headers=house.h("Juli"))
    )
    assert revisions[-1]["reason"] == "member_joined"


def test_roles_and_leaving(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> None:
    frozen_clock.set(datetime(2026, 3, 5, tzinfo=UTC))
    house = make_house(client, make_user, ("Juli", "Franco", "Ana"))
    m = house.members
    r = client.patch(
        house.url(f"/members/{m['Juli']}"), json={"role": "member"}, headers=house.h("Juli")
    )
    assert r.status_code == 409 and r.json()["code"] == "last_admin"
    r = client.post(house.url("/members/me/leave"), headers=house.h("Juli"))
    assert r.status_code == 409 and r.json()["code"] == "last_admin"
    ok(
        client.patch(
            house.url(f"/members/{m['Franco']}"), json={"role": "admin"}, headers=house.h("Juli")
        )
    )
    ok(
        client.patch(
            house.url(f"/members/{m['Juli']}"), json={"role": "member"}, headers=house.h("Franco")
        )
    )
    r = client.patch(
        house.url(f"/members/{m['Ana']}"), json={"role": "admin"}, headers=house.h("Juli")
    )
    assert r.status_code == 403

    left = ok(client.post(house.url("/members/me/leave"), headers=house.h("Ana")))
    ana = next(x for x in left["members"] if x["id"] == m["Ana"])
    assert ana["status"] == "leaving" and ana["left_period_seq"] == 1
    # Ana still takes part in the current period but not in the next one.
    add_expense(client, house, "Juli", amount=900, payer="Juli", date="2026-03-03")
    assert nets(client, house, "1")["Ana"] == -300
    ok(client.post(house.url("/periods/1/close"), headers=house.h("Franco")))
    ok(client.post(house.url("/periods"), headers=house.h("Juli")), 201)
    second = add_expense(client, house, "Juli", amount=900, payer="Juli", date="2026-04-01")
    assert m["Ana"] not in {s["member_id"] for s in second["shares"]}
    # After period 1 is settled, Ana is gone.
    settlement = ok(client.get(house.url("/periods/1/settlement"), headers=house.h("Juli")))
    for t in settlement["transfers"]:
        debtor = next(n for n, mid in m.items() if mid == t["from_member_id"])
        ok(
            client.post(
                house.url(f"/transfers/{t['id']}/confirm"),
                headers=house.h("Juli" if t["to_member_id"] == m["Juli"] else debtor),
            )
        )
    house_after = ok(client.get(house.url(), headers=house.h("Juli")))
    assert next(x for x in house_after["members"] if x["id"] == m["Ana"])["status"] == "left"
    # Former members keep read access only.
    assert client.get(house.url("/periods/1"), headers=house.h("Ana")).status_code == 200
    r = client.post(house.url("/expenses"), json={}, headers=house.h("Ana"))
    assert r.status_code in (403, 422)


def test_former_admin_loses_admin_rights(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> None:
    frozen_clock.set(datetime(2026, 3, 5, tzinfo=UTC))
    house = make_house(client, make_user, ("Juli", "Franco", "Ana"))
    m = house.members
    ok(
        client.patch(
            house.url(f"/members/{m['Franco']}"), json={"role": "admin"}, headers=house.h("Juli")
        )
    )
    # A second admin exists, so Franco may leave while still being an admin.
    ok(client.post(house.url("/members/me/leave"), headers=house.h("Franco")))
    add_expense(client, house, "Juli", amount=900, payer="Juli", date="2026-03-03")
    ok(client.post(house.url("/periods/1/close"), headers=house.h("Juli")))
    ok(client.post(house.url("/periods"), headers=house.h("Juli")), 201)
    settlement = ok(client.get(house.url("/periods/1/settlement"), headers=house.h("Juli")))
    for t in settlement["transfers"]:
        ok(client.post(house.url(f"/transfers/{t['id']}/confirm"), headers=house.h("Juli")))
    house_after = ok(client.get(house.url(), headers=house.h("Franco")))
    franco = next(x for x in house_after["members"] if x["id"] == m["Franco"])
    assert franco["status"] == "left" and franco["role"] == "admin"

    h = house.h("Franco")
    attempts = [
        client.patch(house.url(), json={"name": "Mía"}, headers=h),
        client.post(house.url("/invitations"), headers=h),
        client.delete(house.url("/invitations"), headers=h),
        client.patch(house.url(f"/members/{m['Ana']}"), json={"role": "admin"}, headers=h),
        client.delete(house.url(f"/members/{m['Ana']}"), headers=h),
        client.post(house.url("/categories"), json={"name": "Mascotas"}, headers=h),
        client.put(house.url("/split-rules/default"), json={"split_type": "equal"}, headers=h),
        client.post(
            house.url("/periods/2/reopen"), json={"reason": "take back control"}, headers=h
        ),
    ]
    for r in attempts:
        assert r.status_code == 403, f"{r.request.method} {r.request.url} -> {r.status_code}"
    # Read access remains.
    assert client.get(house.url("/periods/1"), headers=h).status_code == 200


def test_categories_crud(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    house = make_house(client, make_user, ("Juli", "Franco"))
    cat = ok(
        client.post(
            house.url("/categories"),
            json={"name": "Mascotas", "color": "#112233"},
            headers=house.h("Juli"),
        ),
        201,
    )
    r = client.post(house.url("/categories"), json={"name": "mascotas"}, headers=house.h("Juli"))
    assert r.status_code == 409 and r.json()["code"] == "category_exists"
    assert (
        client.post(
            house.url("/categories"), json={"name": "X"}, headers=house.h("Franco")
        ).status_code
        == 403
    )
    upd = ok(
        client.patch(
            house.url(f"/categories/{cat['id']}"), json={"name": "Perro"}, headers=house.h("Juli")
        )
    )
    assert upd["name"] == "Perro"
    ok(client.delete(house.url(f"/categories/{cat['id']}"), headers=house.h("Juli")), 204)
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
    # Default weights 2/1/1.
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
            headers=house.h("Juli"),
        )
    )
    e = add_expense(
        client, house, "Juli", amount=1001, payer="Juli", date="2026-03-02", category="Luz"
    )
    assert [s["amount_cents"] for s in e["shares"]] == [501, 250, 250]
    assert e["split_origin"] == "household_default"
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

    # Changing the category rule re-resolves open-period expenses that follow it.
    ok(
        client.put(
            house.url(f"/categories/{house.categories['Luz']}/split-rule"),
            json={"split_type": "equal"},
            headers=house.h("Juli"),
        )
    )
    luz = ok(client.get(house.url("/expenses?q=Luz"), headers=house.h("Juli")))["items"][0]
    assert luz["split_origin"] == "category"
    assert [s["amount_cents"] for s in luz["shares"]] == [334, 334, 333]

    rules = ok(client.get(house.url("/split-rules"), headers=house.h("Franco")))
    assert rules["categories"] == [
        {"category_id": house.categories["Luz"], "split": {"split_type": "equal", "shares": None}}
    ]

    # Category single rule pointing to a member who is not in the open period -> fallback.
    # Someone joining while no period is open joins the next one: Dani joins while period 1
    # is closed, then period 1 is reopened (nobody paid yet) without Dani in it.
    ok(client.post(house.url("/periods/1/close"), headers=house.h("Franco")))
    dani = make_user("Dani")
    inv = ok(client.post(house.url("/invitations"), headers=house.h("Juli")))
    joined = ok(client.post(f"/v1/invitations/{inv['code']}/accept", headers=dani.headers))
    dani = next(x for x in joined["members"] if x["user_id"] == str(dani.id))
    assert dani["joined_period_seq"] == 2
    dani_id = dani["id"]
    ok(
        client.post(
            house.url("/periods/1/reopen"),
            json={"reason": "Faltan gastos"},
            headers=house.h("Juli"),
        )
    )
    ok(
        client.put(
            house.url(f"/categories/{house.categories['Gas']}/split-rule"),
            json={"split_type": "single", "shares": [{"member_id": dani_id}]},
            headers=house.h("Juli"),
        )
    )
    march = add_expense(
        client, house, "Juli", amount=400, payer="Juli", date="2026-03-03", category="Gas"
    )
    assert march["rule_fallback"] is True and march["split_origin"] == "household_default"
    ok(client.post(house.url("/periods/1/close"), headers=house.h("Franco")))
    ok(client.post(house.url("/periods"), headers=house.h("Ana")), 201)
    april = add_expense(
        client, house, "Juli", amount=400, payer="Juli", date="2026-04-03", category="Gas"
    )
    assert april["rule_fallback"] is False and april["split_origin"] == "category"
    assert april["shares"] == [
        {
            "member_id": dani_id,
            "amount_cents": 400,
            "weight": None,
            "basis_points": None,
            "exact_cents": None,
        }
    ]

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
                        {"member_id": m["Ana"], "amount_cents": 300},
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
