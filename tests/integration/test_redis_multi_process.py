"""Cross-process quota test: each worker owns a separate Redis client and engine.

Set SENTINEL_TEST_REDIS_URL to a dedicated test database (for example DB 15).
This verifies shared Redis state across independent Python processes, not just
async tasks within one event loop.
"""
import asyncio
import multiprocessing
import os
import uuid
from types import SimpleNamespace

import pytest

redis_asyncio = pytest.importorskip("redis.asyncio")
from app.limiter.redis_engine import RedisRateLimitEngine

REDIS_URL = os.getenv("SENTINEL_TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="SENTINEL_TEST_REDIS_URL is not configured")


def _worker_consume(args):
    redis_url, tenant_id, policy_id, algorithm, count = args

    async def run():
        client = redis_asyncio.Redis.from_url(redis_url, decode_responses=True)
        try:
            engine = RedisRateLimitEngine(client)
            policy = SimpleNamespace(
                id=uuid.UUID(policy_id),
                version=1,
                algorithm=algorithm,
                limit_count=10,
                window_seconds=60,
                burst_capacity=10,
            )
            results = await asyncio.gather(*[
                engine.consume(tenant_id=uuid.UUID(tenant_id), policy=policy)
                for _ in range(count)
            ])
            return sum(result.decision.allowed for result in results)
        finally:
            await client.aclose()

    return asyncio.run(run())


@pytest.mark.parametrize("algorithm", ["token_bucket", "fixed_window", "sliding_window"])
def test_quota_is_shared_across_independent_processes(algorithm):
    tenant_id, policy_id = str(uuid.uuid4()), str(uuid.uuid4())
    jobs = [(REDIS_URL, tenant_id, policy_id, algorithm, 20) for _ in range(4)]
    context = multiprocessing.get_context("spawn")
    with context.Pool(processes=4) as pool:
        admitted = pool.map(_worker_consume, jobs)
    assert sum(admitted) == 10
