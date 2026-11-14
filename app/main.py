from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.routes.admin import router as admin_router
from app.api.routes.health import router as health_router
from app.api.routes.identity import router as identity_router
from app.api.routes.metrics import router as metrics_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine
from app.limiter.metrics import RateLimitMetrics
from app.limiter.redis_engine import RedisRateLimitEngine
from app.middleware import RateLimitMiddleware

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    redis_client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )
    app.state.redis = redis_client
    app.state.redis_rate_limit_engine = RedisRateLimitEngine(redis_client)
    app.state.rate_limit_metrics = RateLimitMetrics()
    try:
        yield
    finally:
        await redis_client.aclose()
        await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.4.0",
    description="A distributed multi-tenant API gateway and rate limiter.",
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware, fail_open=settings.rate_limit_fail_open)

app.include_router(health_router)
app.include_router(admin_router)
app.include_router(identity_router)
app.include_router(metrics_router)
