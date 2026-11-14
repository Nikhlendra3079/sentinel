"""Real Redis Lua integration tests.

Set SENTINEL_TEST_REDIS_URL (for example redis://localhost:6379/15) to run.
The tests use random tenant/policy IDs and never flush the selected database.
"""
import asyncio
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
async def test_only_configured_number_of_concurrent_requests_are_admitted(algorithm):
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        engine = RedisRateLimitEngine(redis)
        policy = SimpleNamespace(
            id=uuid.uuid4(), version=1, algorithm=algorithm,
            limit_count=10, window_seconds=60, burst_capacity=10,
        )
        tenant_id = uuid.uuid4()
        executions = await asyncio.gather(*[
            engine.consume(tenant_id=tenant_id, policy=policy)
            for _ in range(50)
        ])
        assert sum(item.decision.allowed for item in executions) == 10
        assert sum(not item.decision.allowed for item in executions) == 40
    finally:
        await redis.aclose()
