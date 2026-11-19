"""Push notifications end to end: tokens, switches, recipients per event, Expo bookkeeping.

The notifier dependency is replaced by one that dispatches right away inside the test's
transaction, with an Expo client over httpx.MockTransport that records every message.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from split_ranch.api.deps import get_notifier
from split_ranch.core import clock
from split_ranch.integrations.expo_push import ExpoPushClient
from split_ranch.models import PushToken
from split_ranch.use_cases.notifications import NotificationEvent, dispatch
from tests.conftest import FrozenClock, TestUser
from tests.integration.helpers import House, add_expense, make_house, ok, pay


@dataclass
class FakeExpo:
    """Records sent messages; tokens in `unregistered` get a DeviceNotRegistered ticket."""

    sent: list[dict[str, Any]] = field(default_factory=list)
    unregistered: set[str] = field(default_factory=set)
    receipts: dict[str, dict[str, Any]] = field(default_factory=dict)
    receipt_requests: list[list[str]] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path.endswith("/getReceipts"):
            self.receipt_requests.append(body["ids"])
            return httpx.Response(
                200, json={"data": {i: self.receipts[i] for i in body["ids"] if i in self.receipts}}
            )
        tickets = []
        for message in body:
            self.sent.append(message)
            if message["to"] in self.unregistered:
                tickets.append({"status": "error", "details": {"error": "DeviceNotRegistered"}})
            else:
                tickets.append({"status": "ok", "id": f"ticket-{len(self.sent)}"})
        return httpx.Response(200, json={"data": tickets})

    def to(self) -> list[str]:
        return [m["to"] for m in self.sent]


class SyncNotifier:
    def __init__(self, session: Session, client: ExpoPushClient) -> None:
        self.session = session
        self.client = client
        self.events: list[NotificationEvent] = []

    def notify(self, event: NotificationEvent) -> None:
        self.events.append(event)
        dispatch(self.session, self.client, event)


@pytest.fixture
def expo() -> FakeExpo:
    return FakeExpo()


@pytest.fixture
def notifier(app: FastAPI, db_session: Session, expo: FakeExpo) -> SyncNotifier:
    sync = SyncNotifier(db_session, ExpoPushClient(transport=httpx.MockTransport(expo.handler)))
    app.dependency_overrides[get_notifier] = lambda: sync
    return sync


def token_of(name: str) -> str:
    return f"ExponentPushToken[{name}]"


def register(client: TestClient, user: TestUser, locale: str = "es") -> None:
    body = {"token": token_of(user.name), "platform": "android", "locale": locale}
    ok(client.put("/v1/me/push-tokens", json=body, headers=user.headers), 204)


@pytest.fixture
def house(
    client: TestClient,
    make_user: Callable[[str], TestUser],
    notifier: SyncNotifier,
    expo: FakeExpo,
) -> House:
    h = make_house(client, make_user)
    for user in h.users.values():
        register(client, user)
    expo.sent.clear()  # joins while building the house notified nobody with a token yet
    return h


# ------------------------------------------------------------ preferences


def test_prefs_default_and_partial_update(client: TestClient, house: House) -> None:
    me = ok(client.get("/v1/me", headers=house.h("Ana")))
    assert me["notifications"] == {
        "enabled": True,
        "expense_created": True,
        "expense_changed": True,
        "payments": True,
        "member_joined": True,
    }
    me = ok(
        client.patch("/v1/me", json={"notifications": {"payments": False}}, headers=house.h("Ana"))
    )
    assert me["notifications"]["payments"] is False
    assert me["notifications"]["expense_created"] is True
    bad = client.patch("/v1/me", json={"notifications": {"nope": True}}, headers=house.h("Ana"))
    assert bad.status_code == 422


# ----------------------------------------------------------------- tokens


def test_token_validation_and_unregister(
    client: TestClient, house: House, db_session: Session
) -> None:
    ana = house.users["Ana"]
    bad = {"token": "not-a-token", "platform": "android"}
    assert client.put("/v1/me/push-tokens", json=bad, headers=ana.headers).status_code == 422

    # Deleting someone else's token does nothing; deleting your own removes it.
    body = {"token": token_of("Ana")}
    ok(client.request("DELETE", "/v1/me/push-tokens", json=body, headers=house.h("Juli")), 204)
    assert db_session.scalar(select(PushToken).where(PushToken.token == token_of("Ana")))
    ok(client.request("DELETE", "/v1/me/push-tokens", json=body, headers=ana.headers), 204)
    assert db_session.scalar(select(PushToken).where(PushToken.token == token_of("Ana"))) is None


def test_same_device_moves_to_the_new_account(
    client: TestClient, house: House, db_session: Session
) -> None:
    body = {"token": token_of("Ana"), "platform": "android", "locale": "en"}
    ok(client.put("/v1/me/push-tokens", json=body, headers=house.h("Franco")), 204)
    rows = db_session.scalars(select(PushToken).where(PushToken.token == token_of("Ana"))).all()
    assert len(rows) == 1
    assert rows[0].user_id == house.users["Franco"].id and rows[0].locale == "en"


# ---------------------------------------------------------------- events


def test_new_expense_notifies_everyone_but_the_author(
    client: TestClient, house: House, expo: FakeExpo
) -> None:
    e = add_expense(
        client, house, "Juli", amount=2340, payer="Juli", date="2026-11-01", description="Súper"
    )
    assert sorted(expo.to()) == [token_of("Ana"), token_of("Franco")]
    message = expo.sent[0]
    assert message["title"] == "Casa"
    assert message["body"] == "Juli agregó «Súper» · 23,40 €"
    assert message["channelId"] == "expenses"
    assert message["data"] == {
        "type": "expense_created",
        "group_id": house.id,
        "url": f"/group/{house.id}/expense/{e['id']}",
    }


def test_idempotent_retry_does_not_notify_again(
    client: TestClient, house: House, expo: FakeExpo
) -> None:
    eid = str(uuid.uuid4())
    add_expense(client, house, "Juli", amount=100, payer="Juli", date="2026-11-01", id=eid)
    add_expense(
        client, house, "Juli", amount=100, payer="Juli", date="2026-11-01", id=eid, expect=200
    )
    assert len(expo.sent) == 2  # Franco and Ana, once


def test_switches_and_language(client: TestClient, house: House, expo: FakeExpo) -> None:
    ok(
        client.patch(
            "/v1/me", json={"notifications": {"expense_created": False}}, headers=house.h("Ana")
        )
    )
    register(client, house.users["Franco"], locale="en")
    add_expense(
        client, house, "Juli", amount=1000, payer="Juli", date="2026-11-01", description="Gas"
    )
    assert expo.to() == [token_of("Franco")]
    assert expo.sent[0]["body"] == "Juli added “Gas” · €10.00"

    off = {"notifications": {"enabled": False}}
    ok(client.patch("/v1/me", json=off, headers=house.h("Franco")))
    expo.sent.clear()
    add_expense(client, house, "Juli", amount=1000, payer="Juli", date="2026-11-01")
    assert expo.sent == []


def test_edit_and_delete_notify_only_involved_members(
    client: TestClient, house: House, expo: FakeExpo
) -> None:
    participants = [house.members["Juli"], house.members["Franco"]]
    e = add_expense(
        client,
        house,
        "Juli",
        amount=1000,
        payer="Juli",
        date="2026-11-01",
        description="Cena",
        participants=participants,
    )
    expo.sent.clear()

    url = house.url(f"/expenses/{e['id']}")
    ok(
        client.patch(
            url, json={"amount_cents": 1200}, headers=house.h("Franco", **{"If-Match": '"1"'})
        )
    )
    assert expo.to() == [token_of("Juli")]  # Ana takes no part; Franco did it
    assert expo.sent[0]["body"] == "Franco editó «Cena» · 12,00 €"
    assert expo.sent[0]["data"]["type"] == "expense_updated"

    expo.sent.clear()
    deleted = client.request("DELETE", url, headers=house.h("Juli", **{"If-Match": '"2"'}))
    assert deleted.status_code == 204
    assert expo.to() == [token_of("Franco")]
    assert expo.sent[0]["data"] == {
        "type": "expense_deleted",
        "group_id": house.id,
        "url": f"/group/{house.id}",
    }


def test_payments_notify_the_other_party(client: TestClient, house: House, expo: FakeExpo) -> None:
    p = pay(client, house, "Franco", payer="Franco", to="Juli", amount=2500)
    assert expo.to() == [token_of("Juli")]
    assert expo.sent[0]["body"] == "Franco te envió 25,00 €. Confírmalo cuando lo recibas"
    assert expo.sent[0]["channelId"] == "payments"
    assert expo.sent[0]["data"]["url"] == f"/group/{house.id}/settle"

    expo.sent.clear()
    url = house.url(f"/payments/{p['id']}/confirm")
    ok(client.post(url, headers=house.h("Juli", **{"If-Match": '"1"'})))
    assert expo.to() == [token_of("Franco")]
    assert expo.sent[0]["data"]["type"] == "payment_confirmed"

    # Cash recorded by the receiver: the payer hears about it.
    expo.sent.clear()
    pay(client, house, "Ana", payer="Franco", to="Ana", amount=500)
    assert expo.to() == [token_of("Franco")]
    assert expo.sent[0]["data"]["type"] == "payment_recorded"


def test_member_joined_notifies_the_group(
    client: TestClient,
    house: House,
    expo: FakeExpo,
    make_user: Callable[[str], TestUser],
) -> None:
    inv = ok(client.post(house.url("/invitations"), headers=house.h("Juli")))
    newcomer = make_user("Lu")
    register(client, newcomer)
    ok(client.post(f"/v1/invitations/{inv['code']}/accept", headers=newcomer.headers))
    assert sorted(expo.to()) == sorted(token_of(n) for n in ("Juli", "Franco", "Ana"))
    assert expo.sent[0]["channelId"] == "group"


def test_members_who_left_are_not_notified(
    client: TestClient, house: House, expo: FakeExpo
) -> None:
    ok(client.post(house.url("/members/me/leave"), headers=house.h("Ana")), 204)
    add_expense(client, house, "Juli", amount=100, payer="Juli", date="2026-11-01")
    assert expo.to() == [token_of("Franco")]


# ------------------------------------------------------- Expo bookkeeping


def test_unregistered_device_is_forgotten(
    client: TestClient, house: House, expo: FakeExpo, db_session: Session
) -> None:
    expo.unregistered.add(token_of("Ana"))
    add_expense(client, house, "Juli", amount=100, payer="Juli", date="2026-11-01")
    assert db_session.scalar(select(PushToken).where(PushToken.token == token_of("Ana"))) is None
    franco = db_session.scalar(select(PushToken).where(PushToken.token == token_of("Franco")))
    assert franco is not None and franco.last_ticket_id is not None


def test_receipts_are_checked_before_the_next_send(
    client: TestClient,
    house: House,
    expo: FakeExpo,
    db_session: Session,
    frozen_clock: FrozenClock,
) -> None:
    start = clock.utcnow()
    frozen_clock.set(start)
    add_expense(client, house, "Juli", amount=100, payer="Juli", date="2026-11-01")
    tokens = {
        t.token: t
        for t in db_session.scalars(select(PushToken).where(PushToken.token.like("%Push%")))
    }
    ana_ticket = tokens[token_of("Ana")].last_ticket_id
    franco_ticket = tokens[token_of("Franco")].last_ticket_id
    assert ana_ticket and franco_ticket
    expo.receipts = {
        ana_ticket: {"status": "error", "details": {"error": "DeviceNotRegistered"}},
        franco_ticket: {"status": "ok"},
    }

    # Too early: receipts are not asked for yet.
    frozen_clock.set(start + timedelta(minutes=5))
    expo.sent.clear()
    add_expense(client, house, "Juli", amount=100, payer="Juli", date="2026-11-01")
    assert expo.receipt_requests == []

    # After 15 minutes: Ana's dead device is dropped before sending.
    frozen_clock.set(start + timedelta(minutes=20))
    expo.sent.clear()
    add_expense(client, house, "Juli", amount=100, payer="Juli", date="2026-11-01")
    assert sorted(expo.receipt_requests[0]) == sorted([ana_ticket, franco_ticket])
    assert expo.to() == [token_of("Franco")]
    db_session.expire_all()
    assert db_session.scalar(select(PushToken).where(PushToken.token == token_of("Ana"))) is None


def test_expo_failure_never_breaks_the_request(
    client: TestClient, house: House, app: FastAPI, db_session: Session
) -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    from split_ranch.use_cases.notifications import dispatch_safely

    class Background:
        def notify(self, event: NotificationEvent) -> None:
            dispatch_safely(
                lambda: _NoCloseSession(db_session),  # type: ignore[arg-type,return-value]
                ExpoPushClient(transport=httpx.MockTransport(failing)),
                event,
            )

    app.dependency_overrides[get_notifier] = Background
    add_expense(client, house, "Juli", amount=100, payer="Juli", date="2026-11-01")


class _NoCloseSession:
    """Context manager over the test session that leaves it open."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def __enter__(self) -> Session:
        return self.session

    def __exit__(self, *exc: object) -> None:
        return None
