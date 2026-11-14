import math
import threading
import time
from dataclasses import dataclass
from typing import Callable

from app.limiter.contracts import RateLimitDecision


@dataclass(frozen=True, slots=True)
class FixedWindowConfig:
    """Immutable fixed-window configuration.

    `limit` is the maximum request cost accepted in each window. `window_seconds`
    is the duration of a window. Windows are aligned to Unix epoch boundaries.
    """

    limit: float
    window_seconds: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.limit) or self.limit <= 0:
            raise ValueError("limit must be a finite number greater than zero")
        if not math.isfinite(self.window_seconds) or self.window_seconds <= 0:
            raise ValueError("window_seconds must be a finite number greater than zero")


@dataclass(slots=True)
class _WindowState:
    window_id: int
    count: float
    updated_at: float


class FixedWindowLimiter:
    """Thread-safe, in-process fixed-window counter.

    Each key has one counter for its current window. Windows are aligned to
    Unix epoch boundaries, so the injected clock must return Unix timestamp
    seconds (normally `time.time`). This is process-local and is not suitable
    for consistent enforcement across multiple workers or machines; a later
    Redis implementation must use one shared clock and atomic operations.

    The last observed timestamp is retained per key. If the wall clock moves
    backwards, the limiter clamps time to that last observation rather than
    accidentally moving a key into an earlier window and granting quota again.
    """

    def __init__(
        self,
        config: FixedWindowConfig,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._clock = clock
        self._states: dict[str, _WindowState] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
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
            effective_now = max(now, state.updated_at) if state else now
            window_id = math.floor(effective_now / self._config.window_seconds)
            window_end = (window_id + 1) * self._config.window_seconds
            reset_after = max(0.0, window_end - effective_now)

            if state is None or window_id > state.window_id:
                state = _WindowState(
                    window_id=window_id,
                    count=0.0,
                    updated_at=effective_now,
                )
                self._states[key] = state
            else:
                # window_id cannot be less than state.window_id because
                # effective_now is clamped to the last observed timestamp.
                state.updated_at = effective_now

            if cost > self._config.limit:
                # No future window can accommodate a request larger than the
                # configured limit, so a numeric retry time would be misleading.
                return self._decision(
                    allowed=False,
                    remaining=max(0.0, self._config.limit - state.count),
                    reset_after=reset_after,
                    retry_after=None,
                )

            if state.count + cost <= self._config.limit:
                state.count += cost
                remaining = self._config.limit - state.count
                return self._decision(
                    allowed=True,
                    remaining=remaining,
                    reset_after=reset_after,
                    retry_after=0.0,
                )

            remaining = max(0.0, self._config.limit - state.count)
            return self._decision(
                allowed=False,
                remaining=remaining,
                reset_after=reset_after,
                retry_after=reset_after,
            )

    def _decision(
        self,
        *,
        allowed: bool,
        remaining: float,
        reset_after: float,
        retry_after: float,
    ) -> RateLimitDecision:
        return RateLimitDecision(
            allowed=allowed,
            limit=self._config.limit,
            remaining=remaining,
            retry_after_seconds=retry_after,
            reset_after_seconds=reset_after,
        )

    def key_count(self) -> int:
        """Return the number of keys currently held (primarily for tests)."""
        return len(self._states)
