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


def month_start(d: date) -> date:
    return d.replace(day=1)


def next_month(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
