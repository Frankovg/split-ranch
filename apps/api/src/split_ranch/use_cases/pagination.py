"""Keyset pagination shared by list endpoints: page size bounds and opaque cursors."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

from split_ranch.core.errors import Unprocessable

DEFAULT_PAGE = 50
MAX_PAGE = 200


def clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_PAGE))


def encode_cursor(fields: dict[str, str]) -> str:
    """URL-safe base64 of the last row's sort key, without padding."""
    raw = json.dumps(fields).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor[T](cursor: str, parse: Callable[[dict[str, Any]], T]) -> T:
    """Decode a cursor and build its sort key with `parse`; any bad input is a 422."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return parse(data)
    except (ValueError, KeyError, TypeError) as exc:
        raise Unprocessable("Invalid cursor") from exc
