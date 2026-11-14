from collections import deque
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from app.limiter.contracts import RateLimitDecision


@dataclass(frozen=True, slots=True)
class SlidingWindowLogConfig:
    """Configuration for a rolling-window request log.

    `limit` is the maximum request cost accepted in any rolling interval
    of `window_seconds`.
    """

    limit: float
    window_seconds: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.limit) or self.limit <= 0:
            raise ValueError("limit must be a finite number greater than zero")
        if not math.isfinite(self.window_seconds) or self.window_seconds <= 0:
            raise ValueError("window_seconds must be a finite number greater than zero")


@dataclass(slots=True)
class _SlidingWindowState:
    # Events are ordered by timestamp and contain (timestamp, request_cost).
    events: deque[tuple[float, float]] = field(default_factory=deque)
    used: float = 0.0
    updated_at: float = 0.0


class SlidingWindowLogLimiter:
    """Thread-safe, in-process sliding-window log limiter.

    Each key retains the timestamp and cost of every admitted request in
    the active rolling window. The interval is (now - window_seconds, now].
    Events at the exact cutoff are expired.

    This implementation is process-local. A multi-worker or multi-machine
    deployment needs shared state and an atomic operation, for example a
    Redis sorted set updated inside a Lua script.
    """

    def __init__(
        self,
        config: SlidingWindowLogConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._clock = clock
        self._states: dict[str, _SlidingWindowState] = {}
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

        with self._lock_for(key):
            now = self._clock()
            if not math.isfinite(now):
                raise ValueError("clock must return a finite timestamp")

            state = self._states.get(key)
            effective_now = max(now, state.updated_at) if state else now
            cutoff = effective_now - self._config.window_seconds

            if state is None:
                state = _SlidingWindowState(updated_at=effective_now)
                self._states[key] = state
            else:
                state.updated_at = effective_now

            # Expire events outside the rolling interval. Using <= means
            # an event exactly window_seconds old no longer counts.
            while state.events and state.events[0][0] <= cutoff:
                _, expired_cost = state.events.popleft()
                state.used -= expired_cost

            # Guard against tiny negative values caused by float arithmetic.
            state.used = max(0.0, state.used)
            remaining = max(0.0, self._config.limit - state.used)
            reset_after = self._reset_after(state, effective_now)

            if cost > self._config.limit:
                return self._decision(
                    allowed=False,
                    remaining=remaining,
                    retry_after=None,
                    reset_after=reset_after,
                )

            if state.used + cost <= self._config.limit:
                state.events.append((effective_now, cost))
                state.used += cost
                return self._decision(
                    allowed=True,
                    remaining=max(0.0, self._config.limit - state.used),
                    retry_after=0.0,
                    reset_after=self._reset_after(state, effective_now),
                )

            retry_after = self._retry_after(state, effective_now, cost)
            return self._decision(
                allowed=False,
                remaining=remaining,
                retry_after=retry_after,
                reset_after=reset_after,
            )

    def _retry_after(
        self,
        state: _SlidingWindowState,
        now: float,
        requested_cost: float,
    ) -> float:
        """Return when enough oldest usage expires to fit this request."""
        usage_after_expiration = state.used
        for timestamp, event_cost in state.events:
            usage_after_expiration -= event_cost
            if usage_after_expiration + requested_cost <= self._config.limit:
                return max(0.0, timestamp + self._config.window_seconds - now)
        # For cost <= limit, expiring every active event must make it fit.
        return max(0.0, state.events[-1][0] + self._config.window_seconds - now)

    def _reset_after(self, state: _SlidingWindowState, now: float) -> float:
        """Seconds until all currently active usage has expired."""
        if not state.events:
            return 0.0
        return max(0.0, state.events[-1][0] + self._config.window_seconds - now)

    def _decision(
        self,
        *,
        allowed: bool,
        remaining: float,
        retry_after: float | None,
        reset_after: float,
    ) -> RateLimitDecision:
        return RateLimitDecision(
            allowed=allowed,
            limit=self._config.limit,
            remaining=remaining,
            retry_after_seconds=retry_after,
            reset_after_seconds=reset_after,
        )

    def key_count(self) -> int:
        """Return the number of keys retained (primarily for tests)."""
        return len(self._states)
