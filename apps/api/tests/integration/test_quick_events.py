"""Quick splits persistence with server-side recomputation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from split_ranch.core.ids import uuid7
from tests.conftest import FrozenClock, TestUser
from tests.integration.helpers import ok


def _trip() -> tuple[dict[str, Any], dict[str, str]]:
    p = {n: str(uuid7()) for n in ("Ana", "Bea", "Carlos")}
    parts = [{"id": p[n], "name": n, "sort_key": i} for i, n in enumerate(p)]
    expenses = [
        {
            "id": str(uuid7()),
            "payer_participant_id": p["Ana"],
            "amount_cents": 30000,
            "description": "Hotel",
            "split_type": "equal",
            "shares": [{"participant_id": p[n], "amount_cents": 10000} for n in p],
        },
        {
            "id": str(uuid7()),
            "payer_participant_id": p["Bea"],
            "amount_cents": 5000,
            "description": "Fuel",
            "split_type": "equal",
            "shares": [
                {"participant_id": p["Ana"], "amount_cents": 2500},
                {"participant_id": p["Bea"], "amount_cents": 2500},
            ],
        },
        {
            "id": str(uuid7()),
            "payer_participant_id": p["Carlos"],
            "amount_cents": 9100,
            "description": "Dinner",
            "split_type": "equal",
            "shares": [
                {"participant_id": p["Ana"], "amount_cents": 3034},
                {"participant_id": p["Bea"], "amount_cents": 3033},
                {"participant_id": p["Carlos"], "amount_cents": 3033},
            ],
        },
    ]
    body = {
        "title": "Viaje",
        "mode": "itemised",
        "participants": parts,
        "expenses": expenses,
        "transfers": [
            {"from_participant_id": p["Bea"], "to_participant_id": p["Ana"], "amount_cents": 10533},
            {
                "from_participant_id": p["Carlos"],
                "to_participant_id": p["Ana"],
                "amount_cents": 3933,
            },
        ],
    }
    return body, p


def test_save_get_list_share(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> None:
    frozen_clock.set(datetime(2026, 3, 5, tzinfo=UTC))
    owner, other = make_user("Ana"), make_user("Bea")
    body, p = _trip()
    eid = str(uuid7())
    r = client.put(f"/v1/quick-events/{eid}", json=body, headers=owner.headers)
    assert r.status_code == 201, r.text
    saved = r.json()
    assert saved["version"] == 1
    nets = {b["participant_id"]: b["net_cents"] for b in saved["balances"]}
    assert nets == {p["Ana"]: 14466, p["Bea"]: -10533, p["Carlos"]: -3933}

    # Owner only.
    assert client.get(f"/v1/quick-events/{eid}", headers=other.headers).status_code == 404
    assert (
        client.put(f"/v1/quick-events/{eid}", json=body, headers=other.headers).status_code == 404
    )
    # If-Match required after first save.
    assert (
        client.put(f"/v1/quick-events/{eid}", json=body, headers=owner.headers).status_code == 428
    )
    body["title"] = "Viaje a Lisboa"
    r = client.put(
        f"/v1/quick-events/{eid}", json=body, headers={**owner.headers, "If-Match": '"1"'}
    )
    assert r.status_code == 200 and r.json()["version"] == 2

    listed = ok(client.get("/v1/quick-events", headers=owner.headers))
    assert (
        listed["items"][0]["title"] == "Viaje a Lisboa"
        and listed["items"][0]["total_cents"] == 44100
    )

    link = ok(client.post(f"/v1/quick-events/{eid}/share", headers=owner.headers))
    assert len(link["share_token"]) == 22 and link["url"].endswith(link["share_token"])
    public = client.get(f"/v1/quick-events/shared/{link['share_token']}")
    assert public.status_code == 200
    shared = public.json()
    assert shared["participants"] == ["Ana", "Bea", "Carlos"]
    assert shared["transfers"][0] == {"from": "Bea", "to": "Ana", "amount_cents": 10533}
    assert "owner_user_id" not in public.text

    frozen_clock.set(datetime(2026, 7, 5, tzinfo=UTC))  # > 90 days later
    assert client.get(f"/v1/quick-events/shared/{link['share_token']}").status_code == 404

    ok(client.delete(f"/v1/quick-events/{eid}", headers=owner.headers), 204)
    assert client.get(f"/v1/quick-events/{eid}", headers=owner.headers).status_code == 404


def test_mismatch_rejected(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    owner = make_user("Ana")
    body, _ = _trip()
    # Order-based rounding instead of largest remainder: wrong cent placement.
    body["expenses"][2]["shares"][0]["amount_cents"] = 3033
    body["expenses"][2]["shares"][2]["amount_cents"] = 3034
    r = client.put(f"/v1/quick-events/{uuid7()}", json=body, headers=owner.headers)
    assert r.status_code == 422 and r.json()["code"] == "split_mismatch"

    body, _ = _trip()
    body["transfers"][0]["amount_cents"] = 10000
    r = client.put(f"/v1/quick-events/{uuid7()}", json=body, headers=owner.headers)
    assert r.status_code == 422 and r.json()["code"] == "split_mismatch"


def test_mode_total_with_payer(client: TestClient, make_user: Callable[[str], TestUser]) -> None:
    owner = make_user("Ana")
    p = {n: str(uuid7()) for n in ("Ana", "Bea", "Carlos", "Dani")}
    body = {
        "title": "Cena viernes",
        "mode": "total",
        "participants": [{"id": p[n], "name": n, "sort_key": i} for i, n in enumerate(p)],
        "expenses": [
            {
                "id": str(uuid7()),
                "payer_participant_id": p["Carlos"],
                "amount_cents": 8750,
                "split_type": "equal",
                "shares": [
                    {"participant_id": p[n], "amount_cents": a}
                    for n, a in zip(p, (2188, 2188, 2187, 2187), strict=True)
                ],
            }
        ],
    }
    saved = ok(client.put(f"/v1/quick-events/{uuid7()}", json=body, headers=owner.headers), 201)
    assert [(t["from_participant_id"], t["amount_cents"]) for t in saved["transfers"]] == [
        (p["Ana"], 2188),
        (p["Bea"], 2188),
        (p["Dani"], 2187),
    ]
