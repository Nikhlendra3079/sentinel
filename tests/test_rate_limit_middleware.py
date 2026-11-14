from types import SimpleNamespace
import uuid

import httpx
import pytest
from fastapi import FastAPI

import app.middleware as middleware_module
from app.limiter.contracts import RateLimitDecision
from app.limiter.metrics import RateLimitMetrics
from app.middleware import RateLimitMiddleware


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def scalars(self, statement):
        return SimpleNamespace(all=lambda: [self.policy])


class FakeEngine:
    def __init__(self, decision):
        self.decision = decision

    async def consume(self, **kwargs):
        return SimpleNamespace(decision=self.decision)


def build_app(monkeypatch, decision, *, fail_open=False):
    tenant = SimpleNamespace(id=uuid.uuid4())
    api_key = SimpleNamespace(id=uuid.uuid4())
    policy = SimpleNamespace(
        id=uuid.uuid4(), algorithm="fixed_window", endpoint_pattern="*",
        is_active=True,
    )
    session = FakeSession()
    session.policy = policy
    monkeypatch.setattr(middleware_module, "AsyncSessionLocal", lambda: session)

    async def fake_authenticate(*args, **kwargs):
        return api_key, tenant

    monkeypatch.setattr(middleware_module, "authenticate_api_key", fake_authenticate)

    app = FastAPI()
    app.state.redis_rate_limit_engine = FakeEngine(decision)
    app.state.rate_limit_metrics = RateLimitMetrics()
    app.add_middleware(RateLimitMiddleware, fail_open=fail_open)

    @app.get("/api/v1/protected/ping")
    async def ping():
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_middleware_adds_rate_limit_headers(monkeypatch):
    app = build_app(monkeypatch, RateLimitDecision(True, 10, 7, 0, 20))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/protected/ping",
            headers={"Authorization": "Bearer sk_live_1234567890abcdef_secret"},
        )
    assert response.status_code == 200
    assert response.headers["RateLimit-Limit"] == "10"
    assert response.headers["RateLimit-Remaining"] == "7"


@pytest.mark.asyncio
async def test_middleware_returns_429_and_retry_after(monkeypatch):
    app = build_app(monkeypatch, RateLimitDecision(False, 10, 0, 2.2, 5))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/protected/ping",
            headers={"Authorization": "Bearer sk_live_1234567890abcdef_secret"},
        )
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "3"
    assert response.json()["detail"] == "Rate limit exceeded"


@pytest.mark.asyncio
async def test_middleware_skips_admin_and_requests_without_bearer(monkeypatch):
    app = build_app(monkeypatch, RateLimitDecision(False, 10, 0, 2, 5))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        public_response = await client.get("/api/v1/protected/ping")
        admin_response = await client.get("/api/v1/admin/not-a-real-route")
    assert public_response.status_code == 200
    assert admin_response.status_code == 404


class FailingEngine:
    async def consume(self, **kwargs):
        from redis.exceptions import RedisError
        raise RedisError("simulated Redis outage")


@pytest.mark.asyncio
async def test_redis_failure_defaults_to_fail_closed_503(monkeypatch):
    app = build_app(monkeypatch, RateLimitDecision(True, 10, 9, 0, 1))
    app.state.redis_rate_limit_engine = FailingEngine()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/protected/ping",
            headers={"Authorization": "Bearer sk_live_1234567890abcdef_secret"},
        )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"


@pytest.mark.asyncio
async def test_redis_failure_can_be_configured_fail_open(monkeypatch):
    app = build_app(monkeypatch, RateLimitDecision(True, 10, 9, 0, 1), fail_open=True)
    app.state.redis_rate_limit_engine = FailingEngine()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/protected/ping",
            headers={"Authorization": "Bearer sk_live_1234567890abcdef_secret"},
        )
    assert response.status_code == 200



@pytest.mark.asyncio
async def test_middleware_records_http_duration_metrics(monkeypatch):
    app = build_app(monkeypatch, RateLimitDecision(True, 10, 9, 0, 1))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/protected/ping",
            headers={"Authorization": "Bearer sk_live_1234567890abcdef_secret"},
        )
    assert response.status_code == 200
    rendered = app.state.rate_limit_metrics.render()
    assert 'sentinel_http_requests_total{method="GET",status_class="2xx"} 1' in rendered
    assert "sentinel_http_request_duration_seconds_count" in rendered
