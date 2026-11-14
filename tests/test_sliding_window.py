from concurrent.futures import ThreadPoolExecutor

import pytest

from app.limiter.sliding_window import (
    SlidingWindowLogConfig,
    SlidingWindowLogLimiter,
)


class FakeClock:
    def __init__(self, initial: float = 0.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_limiter(*, limit: float = 5, window_seconds: float = 10, initial: float = 100):
    clock = FakeClock(initial)
    limiter = SlidingWindowLogLimiter(
        SlidingWindowLogConfig(limit=limit, window_seconds=window_seconds),
        clock=clock,
    )
    return limiter, clock


def test_new_window_starts_with_full_quota() -> None:
    limiter, _ = make_limiter(limit=2)
    first = limiter.consume("tenant-a")
    second = limiter.consume("tenant-a")
    assert first.allowed and second.allowed
    assert [first.remaining, second.remaining] == [1, 0]


def test_denies_when_rolling_window_is_full() -> None:
    limiter, _ = make_limiter(limit=2)
    limiter.consume("tenant-a")
    limiter.consume("tenant-a")
    denied = limiter.consume("tenant-a")
    assert not denied.allowed
    assert denied.remaining == 0
    assert denied.retry_after_seconds == pytest.approx(10)


def test_oldest_event_expires_after_full_window_duration() -> None:
    limiter, clock = make_limiter(limit=1, window_seconds=10)
    assert limiter.consume("tenant-a").allowed
    clock.advance(9.9)
    assert not limiter.consume("tenant-a").allowed
    clock.advance(0.1)
    assert limiter.consume("tenant-a").allowed


def test_exact_cutoff_is_expired() -> None:
    limiter, clock = make_limiter(limit=1, window_seconds=10)
    assert limiter.consume("tenant-a").allowed
    clock.advance(10)
    assert limiter.consume("tenant-a").allowed


def test_window_is_rolling_not_epoch_aligned() -> None:
    limiter, clock = make_limiter(limit=1, window_seconds=10, initial=109.9)
    assert limiter.consume("tenant-a").allowed
    clock.advance(0.2)
    assert not limiter.consume("tenant-a").allowed


def test_retry_after_waits_until_enough_weighted_cost_expires() -> None:
    limiter, clock = make_limiter(limit=5, window_seconds=10)
    assert limiter.consume("tenant-a", cost=2).allowed  # expires at 110
    clock.advance(1)
    assert limiter.consume("tenant-a", cost=2).allowed  # expires at 111
    clock.advance(1)
    assert limiter.consume("tenant-a", cost=1).allowed  # expires at 112

    # Need cost=2: the first event's expiry frees exactly 2 units.
    denied = limiter.consume("tenant-a", cost=2)
    assert not denied.allowed
    assert denied.retry_after_seconds == pytest.approx(8)


def test_weighted_request_consumes_multiple_units() -> None:
    limiter, _ = make_limiter(limit=5)
    decision = limiter.consume("tenant-a", cost=3)
    assert decision.allowed
    assert decision.remaining == 2


def test_request_cost_larger_than_limit_can_never_fit() -> None:
    limiter, _ = make_limiter(limit=2)
    decision = limiter.consume("tenant-a", cost=3)
    assert not decision.allowed
    assert decision.remaining == 2
    assert decision.retry_after_seconds is None


def test_keys_have_independent_logs() -> None:
    limiter, _ = make_limiter(limit=1)
    assert limiter.consume("tenant-a").allowed
    assert not limiter.consume("tenant-a").allowed
    assert limiter.consume("tenant-b").allowed


@pytest.mark.parametrize("cost", [0, -1, float("inf"), float("nan")])
def test_invalid_request_cost_is_rejected(cost: float) -> None:
    limiter, _ = make_limiter()
    with pytest.raises(ValueError):
        limiter.consume("tenant-a", cost=cost)


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        SlidingWindowLogConfig(limit=0, window_seconds=10)
    with pytest.raises(ValueError):
        SlidingWindowLogConfig(limit=5, window_seconds=float("inf"))


def test_empty_key_is_rejected() -> None:
    limiter, _ = make_limiter()
    with pytest.raises(ValueError):
        limiter.consume("")


def test_clock_rollback_does_not_rewind_log() -> None:
    limiter, clock = make_limiter(limit=1, window_seconds=10, initial=109)
    assert limiter.consume("tenant-a").allowed
    clock.now = 0
    assert not limiter.consume("tenant-a").allowed


def test_concurrent_consumption_never_exceeds_limit() -> None:
    limiter, _ = make_limiter(limit=100)
    def attempt(_: int) -> bool:
        return limiter.consume("tenant-concurrent").allowed
    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(attempt, range(1000)))
    assert sum(results) == 100
