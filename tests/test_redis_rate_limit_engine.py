import uuid
from types import SimpleNamespace

import pytest

from app.limiter.redis_engine import RedisRateLimitEngine


class FakeRedis:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def register_script(self, source):
        async def execute(*, keys, args):
            self.calls.append((source, keys, args))
            return self.result
        return execute


def make_policy(algorithm="token_bucket"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        version=3,
        algorithm=algorithm,
        limit_count=10,
        window_seconds=60,
        burst_capacity=12,
    )


@pytest.mark.asyncio
async def test_engine_decodes_redis_script_result_and_builds_versioned_key():
    redis = FakeRedis([1, "4.25", 0, 1500, "12"])
    engine = RedisRateLimitEngine(redis)
    tenant_id = uuid.uuid4()
    policy = make_policy()

    execution = await engine.consume(tenant_id=tenant_id, policy=policy)

    assert execution.policy_id == policy.id
    assert execution.policy_version == 3
    assert execution.algorithm == "token_bucket"
    assert execution.decision.allowed is True
    assert execution.decision.remaining == 4.25
    assert execution.decision.limit == 12
    assert execution.decision.reset_after_seconds == 1.5
    assert len(redis.calls) == 1
    key = redis.calls[0][1][0]
    assert f"{{{tenant_id}:{policy.id}:v3}}" in key


@pytest.mark.asyncio
async def test_sliding_window_keys_share_a_redis_cluster_hash_tag():
    redis = FakeRedis([0, "0", 2500, 3000, "10"])
    engine = RedisRateLimitEngine(redis)
    tenant_id = uuid.uuid4()
    policy = make_policy("sliding_window")

    await engine.consume(tenant_id=tenant_id, policy=policy)

    keys = redis.calls[0][1]
    tags = [key.split("{")[1].split("}")[0] for key in keys]
    assert len(keys) == 4
    assert len(set(tags)) == 1


@pytest.mark.asyncio
async def test_negative_retry_sentinel_means_impossible_request_cost():
    redis = FakeRedis([0, "2", -1, 1000, "5"])
    engine = RedisRateLimitEngine(redis)
    execution = await engine.consume(
        tenant_id=uuid.uuid4(), policy=make_policy(), cost=99,
    )
    assert execution.decision.allowed is False
    assert execution.decision.retry_after_seconds is None
