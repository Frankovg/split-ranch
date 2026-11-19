"""Token-bucket rate limiter."""

from __future__ import annotations

import pytest

from split_ranch.core.rate_limit import RateLimited, RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_a_burst_up_to_the_limit_then_blocks() -> None:
    clock = FakeClock()
    limiter = RateLimiter(3, clock=clock)
    assert [limiter.hit("u") for _ in range(3)] == [None, None, None]
    retry_after = limiter.hit("u")
    assert retry_after == pytest.approx(20.0)  # 3/min: one token every 20 s


def test_refills_over_time() -> None:
    clock = FakeClock()
    limiter = RateLimiter(60, clock=clock)  # one token per second
    for _ in range(60):
        assert limiter.hit("u") is None
    assert limiter.hit("u") is not None
    clock.now += 1
    assert limiter.hit("u") is None
    assert limiter.hit("u") is not None


def test_keys_are_independent() -> None:
    limiter = RateLimiter(1, clock=FakeClock())
    assert limiter.hit("a") is None
    assert limiter.hit("a") is not None
    assert limiter.hit("b") is None


def test_zero_disables() -> None:
    limiter = RateLimiter(0)
    assert not limiter.enabled
    assert all(limiter.hit("u") is None for _ in range(1000))


def test_check_raises_with_retry_after_header() -> None:
    limiter = RateLimiter(1, clock=FakeClock())
    limiter.check("u")
    with pytest.raises(RateLimited) as excinfo:
        limiter.check("u")
    assert excinfo.value.status == 429
    assert excinfo.value.code == "rate_limited"
    assert excinfo.value.headers == {"Retry-After": "60"}


def test_idle_buckets_are_pruned_when_too_many_keys() -> None:
    clock = FakeClock()
    limiter = RateLimiter(60, clock=clock, max_keys=2)
    limiter.hit("a")
    limiter.hit("b")
    clock.now += 60  # both buckets are full again
    limiter.hit("c")
    assert set(limiter._buckets) == {"c"}
