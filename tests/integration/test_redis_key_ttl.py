"""Verify that admitted Redis quota state is assigned an expiry."""
import asyncio
import os
import uuid
from types import SimpleNamespace

import pytest

redis_asyncio = pytest.importorskip("redis.asyncio")
from app.limiter.redis_engine import RedisRateLimitEngine

REDIS_URL = os.getenv("SENTINEL_TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="SENTINEL_TEST_REDIS_URL is not configured")


@pytest.mark.asyncio
@pytest.mark.parametrize("algorithm", ["token_bucket", "fixed_window", "sliding_window"])
async def test_rate_limit_keys_have_positive_ttl(algorithm):
    client = redis_asyncio.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        tenant_id = uuid.uuid4()
        policy = SimpleNamespace(
            id=uuid.uuid4(), version=1, algorithm=algorithm,
            limit_count=10, window_seconds=60, burst_capacity=10,
        )
        engine = RedisRateLimitEngine(client)
        await engine.consume(tenant_id=tenant_id, policy=policy)
        base = engine._base_key(tenant_id, policy, {
            "token_bucket": "tb", "fixed_window": "fw", "sliding_window": "sw"
        }[algorithm])
        keys = {
            "token_bucket": [base],
            "fixed_window": [base],
            "sliding_window": [f"{base}:events", f"{base}:costs", f"{base}:used", f"{base}:clock"],
        }[algorithm]
        ttls = [await client.pttl(key) for key in keys]
        assert all(ttl > 0 for ttl in ttls)
    finally:
        await client.aclose()
