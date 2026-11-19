"""Expo Push client (over httpx.MockTransport) and notification texts."""

from __future__ import annotations

import json

import httpx
import pytest

from split_ranch.integrations.expo_push import (
    EXPO_PUSH_URL,
    EXPO_RECEIPTS_URL,
    ExpoPushClient,
    ExpoPushError,
    PushMessage,
)
from split_ranch.use_cases.notification_texts import format_amount, normalize_locale, render_body


def _message(i: int) -> PushMessage:
    return PushMessage(
        to=f"ExponentPushToken[{i}]",
        title="Casa",
        body="hola",
        channel_id="expenses",
        data={"url": "/group/x"},
    )


def test_send_batches_of_100_and_keeps_order() -> None:
    batches: list[list[dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == EXPO_PUSH_URL
        body = json.loads(request.content)
        batches.append(body)
        return httpx.Response(200, json={"data": [{"status": "ok", "id": m["to"]} for m in body]})

    client = ExpoPushClient(transport=httpx.MockTransport(handler))
    tickets = client.send([_message(i) for i in range(205)])

    assert [len(b) for b in batches] == [100, 100, 5]
    assert [t.id for t in tickets] == [f"ExponentPushToken[{i}]" for i in range(205)]
    first = batches[0][0]
    assert first["channelId"] == "expenses" and first["data"] == {"url": "/group/x"}
    assert first["priority"] == "high"


def test_access_token_header_only_when_set() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"data": [{"status": "ok", "id": "a"}]})

    ExpoPushClient(transport=httpx.MockTransport(handler)).send([_message(1)])
    ExpoPushClient(access_token="secret", transport=httpx.MockTransport(handler)).send(
        [_message(1)]
    )
    assert seen == [None, "Bearer secret"]


def test_ticket_errors_are_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "status": "error",
                        "message": "not registered",
                        "details": {"error": "DeviceNotRegistered"},
                    },
                    {"status": "ok", "id": "r2"},
                ]
            },
        )

    tickets = ExpoPushClient(transport=httpx.MockTransport(handler)).send(
        [_message(1), _message(2)]
    )
    assert tickets[0].status == "error" and tickets[0].error == "DeviceNotRegistered"
    assert tickets[1].status == "ok" and tickets[1].id == "r2"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(200, json={"errors": [{"code": "UNAUTHORIZED", "message": "no"}]}),
        httpx.Response(200, json={"data": []}),  # fewer tickets than messages
    ],
)
def test_request_level_failures_raise(response: httpx.Response) -> None:
    client = ExpoPushClient(transport=httpx.MockTransport(lambda _: response))
    with pytest.raises(ExpoPushError):
        client.send([_message(1)])


def test_network_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    with pytest.raises(ExpoPushError):
        ExpoPushClient(transport=httpx.MockTransport(handler)).send([_message(1)])


def test_get_receipts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == EXPO_RECEIPTS_URL
        assert json.loads(request.content) == {"ids": ["a", "b", "c"]}
        return httpx.Response(
            200,
            json={
                "data": {
                    "a": {"status": "ok"},
                    "b": {"status": "error", "details": {"error": "DeviceNotRegistered"}},
                }
            },
        )

    receipts = ExpoPushClient(transport=httpx.MockTransport(handler)).get_receipts(["a", "b", "c"])
    assert receipts["a"].status == "ok"
    assert receipts["b"].error == "DeviceNotRegistered"
    assert "c" not in receipts


@pytest.mark.parametrize(
    ("cents", "es", "en"),
    [
        (2340, "23,40 €", "€23.40"),
        (5, "0,05 €", "€0.05"),
        (123456789, "1.234.567,89 €", "€1,234,567.89"),
    ],
)
def test_format_amount(cents: int, es: str, en: str) -> None:
    assert format_amount(cents, "es") == es
    assert format_amount(cents, "en") == en


def test_normalize_locale() -> None:
    assert normalize_locale("en") == "en"
    assert normalize_locale("en-GB") == "en"
    assert normalize_locale("es-ES") == "es"
    assert normalize_locale("fr") == "es"
    assert normalize_locale(None) == "es"


def test_render_body() -> None:
    assert (
        render_body("expense_created", "es", actor="Ana", description="Súper", amount_cents=2340)
        == "Ana agregó «Súper» · 23,40 €"
    )
    assert (
        render_body("payment_sent", "en", actor=None, amount_cents=1000)
        == "Someone sent you €10.00. Confirm it once you get it"
    )
    long = render_body("expense_deleted", "es", actor="Ana", description="x" * 100)
    assert "…" in long and len(long) < 100
