import threading
import uuid
from dataclasses import dataclass

from app.limiter.contracts import RateLimitDecision, RateLimiterAlgorithm
from app.limiter.fixed_window import FixedWindowConfig, FixedWindowLimiter
from app.limiter.policy_resolution import resolve_policy
from app.limiter.sliding_window import SlidingWindowLogConfig, SlidingWindowLogLimiter
from app.limiter.token_bucket import TokenBucketConfig, TokenBucketLimiter
from app.models.rate_limit_policy import RateLimitPolicy


@dataclass(frozen=True, slots=True)
class PolicyExecution:
    policy_id: uuid.UUID
    decision: RateLimitDecision


class InProcessRateLimitEngine:
    """Select and execute a policy using process-local algorithm instances.

    Instances are cached by (policy id, version), so a policy update that
    increments version receives fresh algorithm state. This engine is a
    milestone-3 educational implementation, not distributed enforcement.
    """

    def __init__(self) -> None:
        self._instances: dict[tuple[uuid.UUID, int], RateLimiterAlgorithm] = {}
        self._instances_lock = threading.Lock()

    def _algorithm_for(self, policy: RateLimitPolicy) -> RateLimiterAlgorithm:
        cache_key = (policy.id, policy.version)
        with self._instances_lock:
            instance = self._instances.get(cache_key)
            if instance is not None:
                return instance

            if policy.algorithm == "token_bucket":
                capacity = policy.burst_capacity or policy.limit_count
                instance = TokenBucketLimiter(TokenBucketConfig(
                    capacity=float(capacity),
                    refill_rate=policy.limit_count / policy.window_seconds,
                ))
            elif policy.algorithm == "fixed_window":
                instance = FixedWindowLimiter(FixedWindowConfig(
                    limit=float(policy.limit_count), window_seconds=float(policy.window_seconds),
                ))
            elif policy.algorithm == "sliding_window":
                instance = SlidingWindowLogLimiter(SlidingWindowLogConfig(
                    limit=float(policy.limit_count), window_seconds=float(policy.window_seconds),
                ))
            else:
                raise ValueError(f"unsupported rate-limit algorithm: {policy.algorithm}")

            # A policy version change intentionally starts a fresh local quota.
            # Drop stale versions to avoid retaining obsolete limiter state forever.
            for old_key in [key for key in self._instances if key[0] == policy.id]:
                del self._instances[old_key]
            self._instances[cache_key] = instance
            return instance

    def consume(
        self,
        *,
        tenant_id: uuid.UUID,
        policies: list[RateLimitPolicy],
        path: str,
        cost: float = 1.0,
    ) -> PolicyExecution | None:
        policy = resolve_policy(policies, path)
        if policy is None:
            return None
        # Policy identity is part of the key to isolate quotas across policies.
        bucket_key = f"{tenant_id}:{policy.id}"
        decision = self._algorithm_for(policy).consume(bucket_key, cost=cost)
        return PolicyExecution(policy_id=policy.id, decision=decision)
