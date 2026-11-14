import uuid
from types import SimpleNamespace

from app.limiter.engine import InProcessRateLimitEngine


def test_engine_executes_selected_policy_and_enforces_limit():
    tenant_id = uuid.uuid4()
    policy = SimpleNamespace(
        id=uuid.uuid4(), version=1, is_active=True, endpoint_pattern="*",
        algorithm="fixed_window", limit_count=2, window_seconds=60,
        burst_capacity=None,
    )
    engine = InProcessRateLimitEngine()
    first = engine.consume(tenant_id=tenant_id, policies=[policy], path="/v1/test")
    second = engine.consume(tenant_id=tenant_id, policies=[policy], path="/v1/test")
    third = engine.consume(tenant_id=tenant_id, policies=[policy], path="/v1/test")
    assert first and first.decision.allowed
    assert second and second.decision.allowed
    assert third and not third.decision.allowed


def test_engine_returns_none_when_no_policy_matches():
    result = InProcessRateLimitEngine().consume(
        tenant_id=uuid.uuid4(), policies=[], path="/v1/test"
    )
    assert result is None


def test_policy_version_change_creates_fresh_algorithm_state():
    tenant_id = uuid.uuid4()
    policy = SimpleNamespace(
        id=uuid.uuid4(), version=1, is_active=True, endpoint_pattern="*",
        algorithm="fixed_window", limit_count=1, window_seconds=60,
        burst_capacity=None,
    )
    engine = InProcessRateLimitEngine()
    assert engine.consume(tenant_id=tenant_id, policies=[policy], path="/").decision.allowed
    assert not engine.consume(tenant_id=tenant_id, policies=[policy], path="/").decision.allowed
    policy.version = 2
    assert engine.consume(tenant_id=tenant_id, policies=[policy], path="/").decision.allowed
