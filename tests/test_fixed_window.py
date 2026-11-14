from concurrent.futures import ThreadPoolExecutor

import pytest

from app.limiter.fixed_window import FixedWindowConfig, FixedWindowLimiter


class FakeClock:
    def __init__(self, initial: float = 0.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_limiter(*, limit: float = 5, window_seconds: float = 60, initial: float = 0):
    clock = FakeClock(initial)
    limiter = FixedWindowLimiter(
        FixedWindowConfig(limit=limit, window_seconds=window_seconds),
        clock=clock,
    )
    return limiter, clock


def test_window_starts_with_full_quota() -> None:
    limiter, _ = make_limiter(limit=3)

    decisions = [limiter.consume("tenant-a") for _ in range(3)]

    assert all(decision.allowed for decision in decisions)
    assert [decision.remaining for decision in decisions] == [2, 1, 0]


def test_request_is_denied_after_limit_is_reached() -> None:
    limiter, _ = make_limiter(limit=2)
    limiter.consume("tenant-a")
    limiter.consume("tenant-a")

    denied = limiter.consume("tenant-a")

    assert not denied.allowed
    assert denied.remaining == 0
    assert denied.retry_after_seconds == pytest.approx(60)
    assert denied.reset_after_seconds == pytest.approx(60)


def test_counter_resets_at_next_window_boundary() -> None:
    limiter, clock = make_limiter(limit=1, window_seconds=10, initial=5)
    assert limiter.consume("tenant-a").allowed
    assert not limiter.consume("tenant-a").allowed

    clock.advance(5)  # Unix timestamp 10: exactly the next window.
    next_window = limiter.consume("tenant-a")

    assert next_window.allowed
    assert next_window.remaining == 0
    assert next_window.reset_after_seconds == pytest.approx(10)


def test_window_is_aligned_to_epoch_not_first_request_time() -> None:
    limiter, clock = make_limiter(limit=2, window_seconds=10, initial=9)
    assert limiter.consume("tenant-a").allowed

    clock.advance(1)  # timestamp 10 starts a new window.
    decision = limiter.consume("tenant-a")

    assert decision.allowed
    assert decision.remaining == 1


def test_reset_after_counts_down_to_boundary() -> None:
    limiter, clock = make_limiter(limit=2, window_seconds=10, initial=7)

    first = limiter.consume("tenant-a")
    clock.advance(2)
    second = limiter.consume("tenant-a")

    assert first.reset_after_seconds == pytest.approx(3)
    assert second.reset_after_seconds == pytest.approx(1)


def test_keys_have_independent_counters() -> None:
    limiter, _ = make_limiter(limit=1)

    assert limiter.consume("tenant-a").allowed
    assert not limiter.consume("tenant-a").allowed
    assert limiter.consume("tenant-b").allowed


def test_variable_request_cost_is_supported() -> None:
    limiter, _ = make_limiter(limit=5)

    decision = limiter.consume("tenant-a", cost=3)

    assert decision.allowed
    assert decision.remaining == 2


def test_request_cost_that_exceeds_limit_is_denied() -> None:
    limiter, _ = make_limiter(limit=2)

    decision = limiter.consume("tenant-a", cost=3)

    assert not decision.allowed
    assert decision.remaining == 2
    # A request larger than the configured limit can never be admitted.
    assert decision.retry_after_seconds is None


@pytest.mark.parametrize("cost", [0, -1, float("inf"), float("nan")])
def test_invalid_request_cost_is_rejected(cost: float) -> None:
    limiter, _ = make_limiter()
    with pytest.raises(ValueError):
        limiter.consume("tenant-a", cost=cost)


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        FixedWindowConfig(limit=0, window_seconds=60)
    with pytest.raises(ValueError):
        FixedWindowConfig(limit=5, window_seconds=float("inf"))


def test_empty_key_is_rejected() -> None:
    limiter, _ = make_limiter()
    with pytest.raises(ValueError):
        limiter.consume("")


def test_clock_rollback_does_not_grant_a_second_window_quota() -> None:
    limiter, clock = make_limiter(limit=1, window_seconds=10, initial=9)
    assert limiter.consume("tenant-a").allowed

    clock.now = 0  # A faulty/backwards wall clock must not roll state back.
    decision = limiter.consume("tenant-a")

    assert not decision.allowed
    assert decision.remaining == 0


def test_concurrent_consumption_never_exceeds_window_limit() -> None:
    limiter, _ = make_limiter(limit=100)

    def attempt(_: int) -> bool:
        return limiter.consume("tenant-concurrent").allowed

    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(attempt, range(1000)))

    assert sum(results) == 100
