"""Single source of "now" so tests can freeze time (monkeypatch `utcnow`)."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(UTC)


def now() -> datetime:
    """Indirection used by the application; patch `utcnow` in tests."""
    return utcnow()


def today_in(tz: str) -> date:
    return now().astimezone(ZoneInfo(tz)).date()
