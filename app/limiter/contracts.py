from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Outcome of one rate-limit attempt.

    `remaining` and `limit` are expressed in request-cost units (tokens for
    token bucket). `retry_after_seconds=None` means the requested cost can
    never fit in the configured bucket, rather than merely needing to wait.
    """

    allowed: bool
    limit: float
    remaining: float
    retry_after_seconds: float | None
    reset_after_seconds: float


class RateLimiterAlgorithm(Protocol):
    """Common interface implemented by each rate-limiting algorithm."""

    def consume(self, key: str, *, cost: float = 1.0) -> RateLimitDecision:
        """Atomically evaluate and, when allowed, consume request capacity."""
        ...
