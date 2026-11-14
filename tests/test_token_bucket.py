from concurrent.futures import ThreadPoolExecutor

import pytest

from app.limiter.policy_mapping import token_bucket_config_from_policy
from app.limiter.token_bucket import TokenBucketConfig, TokenBucketLimiter


class FakeClock:
    def __init__(self, initial: float = 0.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_limiter(*, capacity: float = 10, refill_rate: float = 2):
    clock = FakeClock()
    limiter = TokenBucketLimiter(
        TokenBucketConfig(capacity=capacity, refill_rate=refill_rate),
        clock=clock,
    )
    return limiter, clock


def test_bucket_starts_full_and_consumes_tokens() -> None:
    limiter, _ = make_limiter(capacity=3)

    assert limiter.consume("tenant-a").remaining == 2
    assert limiter.consume("tenant-a").remaining == 1
    assert limiter.consume("tenant-a").remaining == 0
    denied = limiter.consume("tenant-a")

    assert denied.allowed is False
    assert denied.remaining == 0
    assert denied.retry_after_seconds == pytest.approx(0.5)


def test_tokens_refill_over_elapsed_time() -> None:
    limiter, clock = make_limiter(capacity=10, refill_rate=2)
    for _ in range(10):
        assert limiter.consume("tenant-a").allowed

    clock.advance(1.5)
    decision = limiter.consume("tenant-a")

    assert decision.allowed is True
    assert decision.remaining == pytest.approx(2.0)


def test_refill_never_exceeds_capacity() -> None:
    limiter, clock = make_limiter(capacity=5, refill_rate=2)
    clock.advance(100)

    decision = limiter.consume("tenant-a")

    assert decision.allowed is True
    assert decision.remaining == 4


def test_denied_requests_do_not_double_count_elapsed_time() -> None:
    limiter, clock = make_limiter(capacity=1, refill_rate=1)
    limiter.consume("tenant-a")

    clock.advance(0.25)
    first = limiter.consume("tenant-a")
    second = limiter.consume("tenant-a")

    assert first.retry_after_seconds == pytest.approx(0.75)
    assert second.retry_after_seconds == pytest.approx(0.75)


def test_buckets_are_isolated_by_key() -> None:
    limiter, _ = make_limiter(capacity=1)

    assert limiter.consume("tenant-a").allowed
    assert not limiter.consume("tenant-a").allowed
    assert limiter.consume("tenant-b").allowed


def test_request_cost_can_be_greater_than_one() -> None:
    limiter, _ = make_limiter(capacity=5, refill_rate=1)

    decision = limiter.consume("tenant-a", cost=3)

    assert decision.allowed
    assert decision.remaining == 2


def test_cost_larger_than_capacity_can_never_be_allowed() -> None:
    limiter, _ = make_limiter(capacity=2, refill_rate=1)

    decision = limiter.consume("tenant-a", cost=3)

    assert not decision.allowed
    assert decision.retry_after_seconds is None


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        TokenBucketConfig(capacity=0, refill_rate=1)
    with pytest.raises(ValueError):
        TokenBucketConfig(capacity=1, refill_rate=float("inf"))


@pytest.mark.parametrize("cost", [0, -1, float("inf"), float("nan")])
def test_invalid_request_cost_is_rejected(cost: float) -> None:
    limiter, _ = make_limiter()
    with pytest.raises(ValueError):
        limiter.consume("tenant-a", cost=cost)


def test_empty_bucket_key_is_rejected() -> None:
    limiter, _ = make_limiter()
    with pytest.raises(ValueError):
        limiter.consume("")


def test_clock_moving_backwards_does_not_create_tokens() -> None:
    limiter, clock = make_limiter(capacity=1, refill_rate=1)
    limiter.consume("tenant-a")
    clock.now = -100

    decision = limiter.consume("tenant-a")

    assert not decision.allowed
    assert decision.remaining == 0


def test_policy_fields_map_to_token_bucket_configuration() -> None:
    config = token_bucket_config_from_policy(
        limit_count=100,
        window_seconds=60,
        burst_capacity=150,
    )

    assert config.capacity == 150
    assert config.refill_rate == pytest.approx(100 / 60)


def test_concurrent_consumption_never_exceeds_initial_capacity() -> None:
    limiter, _ = make_limiter(capacity=100, refill_rate=1)

    def attempt(_: int) -> bool:
        return limiter.consume("tenant-concurrent").allowed

    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(attempt, range(1000)))

    assert sum(results) == 100
