"""Expo Push Service client (https://docs.expo.dev/push-notifications/sending-notifications/).

Two calls: `send` (up to 100 messages per request, one ticket per message in the same order)
and `get_receipts` (delivery result for ticket ids, available for 24 h). When
`access_token` is set it is sent as a bearer token, which Expo requires once "enhanced
security for push notifications" is turned on for the account.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
MAX_MESSAGES_PER_REQUEST = 100
MAX_RECEIPT_IDS_PER_REQUEST = 1000
DEVICE_NOT_REGISTERED = "DeviceNotRegistered"


class ExpoPushError(Exception):
    """The whole request failed (network error, non-2xx status or a request-level error)."""


@dataclass(frozen=True)
class PushMessage:
    to: str
    title: str
    body: str
    channel_id: str
    data: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "to": self.to,
            "title": self.title,
            "body": self.body,
            "data": self.data,
            "channelId": self.channel_id,
            "sound": "default",
            "priority": "high",
        }


@dataclass(frozen=True)
class PushTicket:
    """`status` is 'ok' (with `id`, the receipt id) or 'error' (with `error`, e.g.
    DeviceNotRegistered)."""

    status: str
    id: str | None = None
    error: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class PushReceipt:
    status: str
    error: str | None = None
    message: str | None = None


def _chunks[T](items: Sequence[T], size: int) -> list[Sequence[T]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class ExpoPushClient:
    def __init__(
        self,
        *,
        access_token: str | None = None,
        timeout_seconds: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"Accept": "application/json", "Accept-Encoding": "gzip, deflate"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        self._client = httpx.Client(
            headers=headers, timeout=httpx.Timeout(timeout_seconds), transport=transport
        )

    def close(self) -> None:
        self._client.close()

    def _post(self, url: str, payload: object) -> dict[str, Any]:
        try:
            response = self._client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise ExpoPushError(f"Expo push request failed: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            raise ExpoPushError(f"Expo push request failed with status {response.status_code}")
        body: Any = response.json()
        if not isinstance(body, dict):
            raise ExpoPushError("Unexpected Expo push response")
        if body.get("errors"):
            codes = ", ".join(str(e.get("code")) for e in body["errors"] if isinstance(e, dict))
            raise ExpoPushError(f"Expo push request rejected: {codes or 'unknown error'}")
        return body

    def send(self, messages: Sequence[PushMessage]) -> list[PushTicket]:
        """One ticket per message, in order. Batches of 100 (Expo's limit per request)."""
        tickets: list[PushTicket] = []
        for chunk in _chunks(messages, MAX_MESSAGES_PER_REQUEST):
            body = self._post(EXPO_PUSH_URL, [m.to_json() for m in chunk])
            data = body.get("data")
            if not isinstance(data, list) or len(data) != len(chunk):
                raise ExpoPushError("Expo push response does not match the request")
            for raw in data:
                details = raw.get("details") or {}
                tickets.append(
                    PushTicket(
                        status=str(raw.get("status")),
                        id=raw.get("id"),
                        error=details.get("error") if isinstance(details, dict) else None,
                        message=raw.get("message"),
                    )
                )
        return tickets

    def get_receipts(self, ids: Sequence[str]) -> dict[str, PushReceipt]:
        """Receipts by ticket id; ids without a receipt (yet, or any more) are missing."""
        receipts: dict[str, PushReceipt] = {}
        for chunk in _chunks(ids, MAX_RECEIPT_IDS_PER_REQUEST):
            body = self._post(EXPO_RECEIPTS_URL, {"ids": list(chunk)})
            data = body.get("data") or {}
            if not isinstance(data, dict):
                raise ExpoPushError("Unexpected Expo receipts response")
            for receipt_id, raw in data.items():
                details = raw.get("details") or {}
                receipts[receipt_id] = PushReceipt(
                    status=str(raw.get("status")),
                    error=details.get("error") if isinstance(details, dict) else None,
                    message=raw.get("message"),
                )
        return receipts
