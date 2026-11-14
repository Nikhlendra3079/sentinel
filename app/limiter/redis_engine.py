from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

from app.limiter.contracts import RateLimitDecision
from app.limiter.lua.fixed_window import FIXED_WINDOW_LUA
from app.limiter.lua.sliding_window import SLIDING_WINDOW_LUA
from app.limiter.lua.token_bucket import TOKEN_BUCKET_LUA
from app.models.rate_limit_policy import RateLimitPolicy


@dataclass(frozen=True, slots=True)
class DistributedPolicyExecution:
    policy_id: uuid.UUID
    policy_version: int
    algorithm: str
    decision: RateLimitDecision


def _seconds(milliseconds: int | float) -> float | None:
    if milliseconds < 0:
        return None
    return milliseconds / 1000.0


def _format_number(value: float) -> str:
    return format(float(value), ".17g")


class RedisRateLimitEngine:
    """Execute rate-limit policies atomically against shared Redis state.

    Redis server TIME is authoritative for all algorithms, so application
    worker clock skew does not change quota decisions. Policy versions are
    part of the key namespace: a policy update starts a fresh quota while old
    keys expire naturally.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._token_bucket = redis.register_script(TOKEN_BUCKET_LUA)
        self._fixed_window = redis.register_script(FIXED_WINDOW_LUA)
        self._sliding_window = redis.register_script(SLIDING_WINDOW_LUA)

    @staticmethod
    def _base_key(tenant_id: uuid.UUID, policy: RateLimitPolicy, algorithm: str) -> str:
        # The hash tag keeps all keys for one tenant-policy-version in one
        # Redis Cluster slot, which is required for multi-key Lua scripts.
        tag = f"{tenant_id}:{policy.id}:v{policy.version}"
        return f"sentinel:rl:{{{tag}}}:{algorithm}"

    @staticmethod
    def _decision(raw: Any) -> RateLimitDecision:
        if not isinstance(raw, (list, tuple)) or len(raw) != 5:
            raise RuntimeError("Redis rate-limit script returned an invalid response")
        allowed, remaining, retry_ms, reset_ms, limit = raw
        retry_seconds = _seconds(float(retry_ms))
        return RateLimitDecision(
            allowed=bool(int(allowed)),
            limit=float(limit),
            remaining=max(0.0, float(remaining)),
            retry_after_seconds=retry_seconds,
            reset_after_seconds=max(0.0, float(reset_ms) / 1000.0),
        )

    async def consume(
        self,
        *,
        tenant_id: uuid.UUID,
        policy: RateLimitPolicy,
        cost: float = 1.0,
    ) -> DistributedPolicyExecution:
        if not math.isfinite(cost) or cost <= 0:
            raise ValueError("cost must be a finite number greater than zero")
        if policy.algorithm == "token_bucket":
            capacity = float(policy.burst_capacity or policy.limit_count)
            refill_per_ms = policy.limit_count / policy.window_seconds / 1000.0
            full_refill_ms = capacity / refill_per_ms
            ttl_ms = max(1000, math.ceil(full_refill_ms * 2))
            raw = await self._token_bucket(
                keys=[self._base_key(tenant_id, policy, "tb")],
                args=[
                    _format_number(capacity),
                    _format_number(refill_per_ms),
                    _format_number(cost),
                    ttl_ms,
                ],
            )
        elif policy.algorithm == "fixed_window":
            window_ms = policy.window_seconds * 1000
            raw = await self._fixed_window(
                keys=[self._base_key(tenant_id, policy, "fw")],
                args=[policy.limit_count, window_ms, _format_number(cost)],
            )
        elif policy.algorithm == "sliding_window":
            window_ms = policy.window_seconds * 1000
            base = self._base_key(tenant_id, policy, "sw")
            ttl_ms = max(1000, window_ms * 2)
            raw = await self._sliding_window(
                keys=[f"{base}:events", f"{base}:costs", f"{base}:used", f"{base}:clock"],
                args=[
                    policy.limit_count,
                    window_ms,
                    _format_number(cost),
                    uuid.uuid4().hex,
                    ttl_ms,
                ],
            )
        else:
            raise ValueError(f"unsupported rate-limit algorithm: {policy.algorithm}")

        return DistributedPolicyExecution(
            policy_id=policy.id,
            policy_version=policy.version,
            algorithm=policy.algorithm,
            decision=self._decision(raw),
        )
