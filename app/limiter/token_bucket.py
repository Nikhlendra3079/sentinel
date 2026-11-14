import math
import threading
import time
from dataclasses import dataclass
from typing import Callable

from app.limiter.contracts import RateLimitDecision


@dataclass(frozen=True, slots=True)
class TokenBucketConfig:
    """Immutable token-bucket configuration.

    refill_rate is measured in tokens per second. Capacity is the maximum
    number of tokens the bucket can hold.
    """

    capacity: float
    refill_rate: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.capacity) or self.capacity <= 0:
            raise ValueError("capacity must be a finite number greater than zero")
        if not math.isfinite(self.refill_rate) or self.refill_rate <= 0:
            raise ValueError("refill_rate must be a finite number greater than zero")


@dataclass(slots=True)
class _BucketState:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    """Thread-safe, in-process token bucket implementation.

    This implementation is deliberately process-local. It is useful for
    understanding and testing the algorithm, but does NOT enforce a shared
    quota across multiple worker processes or machines. Redis-backed atomic
    execution is a later milestone.

    `clock` must return seconds from a monotonic time source. It is injectable
    so tests can advance time deterministically without sleeping.
    """

    def __init__(
        self,
        config: TokenBucketConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._clock = clock
        self._states: dict[str, _BucketState] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
        # The lock dictionary itself needs protection: two threads must not
        # create different locks for the same previously unseen bucket key.
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def consume(self, key: str, *, cost: float = 1.0) -> RateLimitDecision:
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        if not math.isfinite(cost) or cost <= 0:
            raise ValueError("cost must be a finite number greater than zero")

        lock = self._lock_for(key)
        with lock:
            now = self._clock()
            if not math.isfinite(now):
                raise ValueError("clock must return a finite timestamp")

            state = self._states.get(key)
            if state is None:
                state = _BucketState(
                    tokens=self._config.capacity,
                    updated_at=now,
                )
                self._states[key] = state

            # Monotonic clocks should not move backwards. max() also makes the
            # state robust to a faulty injected test clock.
            effective_now = max(now, state.updated_at)
            elapsed = effective_now - state.updated_at
            replenished = min(
                self._config.capacity,
                state.tokens + elapsed * self._config.refill_rate,
            )

            # Persist the refill calculation on both allow and deny paths.
            # Otherwise repeated rejected requests could count the same time
            # interval more than once.
            state.tokens = replenished
            state.updated_at = effective_now

            # A request larger than capacity can never succeed, regardless of
            # how long the caller waits. Do not report a misleading retry time.
            if cost > self._config.capacity:
                return self._decision(
                    allowed=False,
                    remaining=replenished,
                    retry_after=None,
                )

            if replenished >= cost:
                state.tokens = replenished - cost
                return self._decision(
                    allowed=True,
                    remaining=state.tokens,
                    retry_after=0.0,
                )

            missing = cost - replenished
            retry_after = missing / self._config.refill_rate
            return self._decision(
                allowed=False,
                remaining=replenished,
                retry_after=retry_after,
            )

    def _decision(
        self,
        *,
        allowed: bool,
        remaining: float,
        retry_after: float | None,
    ) -> RateLimitDecision:
        reset_after = (self._config.capacity - remaining) / self._config.refill_rate
        return RateLimitDecision(
            allowed=allowed,
            limit=self._config.capacity,
            remaining=remaining,
            retry_after_seconds=retry_after,
            reset_after_seconds=max(0.0, reset_after),
        )

    def bucket_count(self) -> int:
        """Return the number of keys currently held (primarily for tests)."""
        return len(self._states)
