"""Process-local per-key rate limiting (token bucket).

The API runs as a single process (docs/00), so an in-memory limiter is enough: no Redis.
With several processes each one would enforce the limit on its own share of traffic.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Hashable

from split_ranch.core.errors import AppError

# Above this many tracked keys, idle (full) buckets are dropped to bound memory.
MAX_TRACKED_KEYS = 10_000


class RateLimited(AppError):
    status = 429
    code = "rate_limited"
    title = "Too many requests"


class RateLimiter:
    """Token bucket per key: bursts up to `per_minute`, refilled at `per_minute` per minute.

    `per_minute <= 0` disables the limiter.
    """

    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = MAX_TRACKED_KEYS,
    ) -> None:
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0  # tokens per second
        self._clock = clock
        self._max_keys = max_keys
        self._lock = threading.Lock()
        self._buckets: dict[Hashable, tuple[float, float]] = {}  # key -> (tokens, updated_at)

    @property
    def enabled(self) -> bool:
        return self.capacity > 0

    def hit(self, key: Hashable) -> float | None:
        """Takes one token for `key`. Returns None if allowed, else seconds until the next one."""
        if not self.enabled:
            return None
        now = self._clock()
        with self._lock:
            tokens = self._current(key, now)
            if tokens >= 1:
                if key not in self._buckets and len(self._buckets) >= self._max_keys:
                    self._prune(now)
                self._buckets[key] = (tokens - 1, now)
                return None
            self._buckets[key] = (tokens, now)
            return (1 - tokens) / self.rate

    def check(self, key: Hashable) -> None:
        """Like `hit`, but raises RateLimited (429 with Retry-After) when over the limit."""
        retry_after = self.hit(key)
        if retry_after is not None:
            raise RateLimited(
                "Too many requests, try again later",
                headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
            )

    def _current(self, key: Hashable, now: float) -> float:
        bucket = self._buckets.get(key)
        if bucket is None:
            return self.capacity
        tokens, updated_at = bucket
        return min(self.capacity, tokens + (now - updated_at) * self.rate)

    def _prune(self, now: float) -> None:
        full = [k for k in self._buckets if self._current(k, now) >= self.capacity]
        for k in full:
            del self._buckets[k]
