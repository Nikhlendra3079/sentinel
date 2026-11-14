"""Redis TTL and memory-accounting integration checks.

Set SENTINEL_TEST_REDIS_URL to a dedicated test database.
"""
import os
import uuid
from types import SimpleNamespace

import pytest

redis_asyncio = pytest.importorskip("redis.asyncio")
Redis = redis_asyncio.Redis

from app.limiter.redis_engine import RedisRateLimitEngine

REDIS_URL = os.getenv("SENTINEL_TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="SENTINEL_TEST_REDIS_URL is not configured")


@pytest.mark.asyncio
@pytest.mark.parametrize("algorithm", ["token_bucket", "fixed_window", "sliding_window"])
async def test_rate_limit_keys_have_positive_ttl_and_memory_usage(algorithm):
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        engine = RedisRateLimitEngine(redis)
        policy = SimpleNamespace(
            id=uuid.uuid4(), version=1, algorithm=algorithm,
            limit_count=10, window_seconds=60, burst_capacity=10,
        )
        tenant_id = uuid.uuid4()
        await engine.consume(tenant_id=tenant_id, policy=policy)

        if algorithm == "token_bucket":
            keys = [engine._base_key(tenant_id, policy, "tb")]
        elif algorithm == "fixed_window":
            keys = [engine._base_key(tenant_id, policy, "fw")]
        else:
            base = engine._base_key(tenant_id, policy, "sw")
            keys = [f"{base}:events", f"{base}:costs", f"{base}:used", f"{base}:clock"]

        for key in keys:
            ttl = await redis.pttl(key)
            assert ttl > 0, f"expected expiring key, got PTTL={ttl} for {key}"
            assert await redis.memory_usage(key) is not None
    finally:
        await redis.aclose()
