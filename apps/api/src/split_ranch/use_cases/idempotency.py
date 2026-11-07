"""Idempotency-Key support for creating endpoints (keys kept 48 h)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from split_ranch.core import clock
from split_ranch.core.errors import Unprocessable
from split_ranch.models import IdempotencyKey

RETENTION = timedelta(hours=48)


@dataclass(frozen=True)
class StoredResponse:
    status: int
    body: dict[str, Any]


def request_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def lookup(
    session: Session, user_id: UUID, key: str | None, endpoint: str, payload_hash: str
) -> StoredResponse | None:
    if not key:
        return None
    row = session.scalars(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.key == key,
            IdempotencyKey.created_at > clock.now() - RETENTION,
        )
    ).first()
    if row is None:
        return None
    if row.request_hash != payload_hash or row.endpoint != endpoint:
        raise Unprocessable(
            "Idempotency-Key was already used with a different request",
            code="idempotency_key_reuse",
        )
    return StoredResponse(row.response_status, row.response_body)


def store(
    session: Session,
    user_id: UUID,
    key: str | None,
    endpoint: str,
    payload_hash: str,
    status: int,
    body: dict[str, Any],
) -> None:
    if not key:
        return
    # Expired keys of this user can be reused: remove them first.
    session.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.key == key,
            IdempotencyKey.created_at <= clock.now() - RETENTION,
        )
    )
    session.add(
        IdempotencyKey(
            user_id=user_id,
            key=key,
            endpoint=endpoint,
            request_hash=payload_hash,
            response_status=status,
            response_body=body,
        )
    )


def purge_expired(session: Session) -> int:
    result = session.execute(
        delete(IdempotencyKey).where(IdempotencyKey.created_at <= clock.now() - RETENTION)
    )
    session.commit()
    return int(getattr(result, "rowcount", 0) or 0)
