"""The process-local ensure_user cache stays bounded."""

from __future__ import annotations

import uuid

import pytest

from split_ranch.use_cases import users
from split_ranch.use_cases.users import _EnsureUserCache

FP = ("a@example.com", "Ana", None)


def test_hit_and_miss() -> None:
    cache = _EnsureUserCache()
    uid = uuid.uuid4()
    assert not cache.fresh(uid, FP, ttl=60)
    cache.remember(uid, FP, ttl=60)
    assert cache.fresh(uid, FP, ttl=60)
    assert not cache.fresh(uid, ("other@example.com", "Ana", None), ttl=60)


def test_never_grows_past_max_entries() -> None:
    cache = _EnsureUserCache(max_entries=3)
    ids = [uuid.uuid4() for _ in range(10)]
    for uid in ids:
        cache.remember(uid, FP, ttl=60)
        assert len(cache) <= 3
    # The newest entry always survives.
    assert cache.fresh(ids[-1], FP, ttl=60)


def test_expired_entries_are_dropped_first(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(users.time, "monotonic", lambda: now[0])
    cache = _EnsureUserCache(max_entries=2)
    expired, live, new = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    cache.remember(expired, FP, ttl=10)
    cache.remember(live, FP, ttl=60)
    now[0] += 30  # `expired` is past its TTL, `live` is not
    cache.remember(new, FP, ttl=60)
    assert cache.fresh(live, FP, ttl=60)
    assert cache.fresh(new, FP, ttl=60)
    assert len(cache) == 2
