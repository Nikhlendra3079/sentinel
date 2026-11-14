import logging
import math
import time
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.security import extract_public_prefix
from app.db.session import AsyncSessionLocal
from app.limiter.policy_resolution import resolve_policy
from app.models.rate_limit_policy import RateLimitPolicy
from app.schemas.principal import TenantPrincipal
from app.services.api_key_service import authenticate_api_key

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Authenticate tenant bearer requests and enforce their selected policy.

    Admin, health, documentation, and non-API paths are not rate-limited here.
    A valid principal is placed on request.state so FastAPI dependencies can
    reuse the authenticated identity rather than querying PostgreSQL twice.
    """

    def __init__(self, app, *, fail_open: bool = False) -> None:
        super().__init__(app)
        self._fail_open = fail_open

    @staticmethod
    def _eligible_path(path: str) -> bool:
        return (
            path.startswith("/api/v1/")
            and path != "/api/v1/admin"
            and not path.startswith("/api/v1/admin/")
        )

    @staticmethod
    def _format(value: float) -> str:
        return str(max(0, math.floor(value)))

    @staticmethod
    def _decision_headers(decision) -> dict[str, str]:
        return {
            "RateLimit-Limit": RateLimitMiddleware._format(decision.limit),
            "RateLimit-Remaining": RateLimitMiddleware._format(decision.remaining),
            "RateLimit-Reset": str(max(0, math.ceil(decision.reset_after_seconds))),
            "X-RateLimit-Limit": RateLimitMiddleware._format(decision.limit),
            "X-RateLimit-Remaining": RateLimitMiddleware._format(decision.remaining),
            "X-RateLimit-Reset": str(max(0, math.ceil(decision.reset_after_seconds))),
        }

    async def _dependency_unavailable(self, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": detail},
            headers={"Retry-After": "1"},
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        started = time.perf_counter()
        status_code = 500
        try:
            response = await self._dispatch(request, call_next)
            status_code = response.status_code
            return response
        finally:
            metrics = getattr(request.app.state, "rate_limit_metrics", None)
            if metrics is not None:
                metrics.observe_http_request(
                    time.perf_counter() - started,
                    request.method,
                    status_code,
                )

    async def _dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if not self._eligible_path(request.url.path):
            return await call_next(request)

        authorization = request.headers.get("authorization", "")
        scheme, separator, presented_key = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not presented_key:
            return await call_next(request)

        public_prefix = extract_public_prefix(presented_key)
        if public_prefix is None:
            return await call_next(request)

        # Authentication and policy reads remain database-backed. A database
        # outage must not be treated as a rate-limit fail-open condition.
        principal = None
        policies = []
        try:
            async with AsyncSessionLocal() as session:
                authenticated = await authenticate_api_key(
                    session,
                    public_prefix=public_prefix,
                    presented_key=presented_key,
                )
                if authenticated is not None:
                    api_key, tenant = authenticated
                    principal = TenantPrincipal(tenant_id=tenant.id, api_key_id=api_key.id)
                    result = await session.scalars(
                        select(RateLimitPolicy).where(
                            RateLimitPolicy.tenant_id == tenant.id,
                            RateLimitPolicy.is_active.is_(True),
                        )
                    )
                    policies = list(result.all())
        except SQLAlchemyError:
            logger.exception(
                "database unavailable during tenant authentication or policy lookup"
            )
            return await self._dependency_unavailable(
                "Authentication service temporarily unavailable"
            )

        if principal is None:
            return await call_next(request)
        request.state.tenant_principal = principal

        try:
            policy = resolve_policy(policies, request.url.path)
        except ValueError:
            logger.exception("ambiguous rate-limit policy configuration")
            return JSONResponse(
                status_code=500,
                content={"detail": "Invalid rate-limit policy configuration"},
            )

        if policy is None:
            return await call_next(request)

        try:
            execution = await request.app.state.redis_rate_limit_engine.consume(
                tenant_id=principal.tenant_id,
                policy=policy,
                cost=1.0,
            )
        except (RedisError, TimeoutError, OSError):
            metrics = getattr(request.app.state, "rate_limit_metrics", None)
            if metrics is not None:
                outcome = (
                    "redis_error_fail_open"
                    if self._fail_open
                    else "redis_error_fail_closed"
                )
                metrics.increment(policy.algorithm, outcome)
            logger.exception(
                "Redis rate-limit execution failed",
                extra={"algorithm": policy.algorithm},
            )
            if self._fail_open:
                return await call_next(request)
            return await self._dependency_unavailable(
                "Rate-limiting service temporarily unavailable"
            )

        decision = execution.decision
        metrics = getattr(request.app.state, "rate_limit_metrics", None)
        if metrics is not None:
            metrics.increment(policy.algorithm, "allowed" if decision.allowed else "denied")

        headers = self._decision_headers(decision)
        if not decision.allowed:
            retry_after = decision.retry_after_seconds
            if retry_after is not None:
                headers["Retry-After"] = str(max(1, math.ceil(retry_after)))
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "policy_id": str(policy.id),
                    "algorithm": policy.algorithm,
                },
                headers=headers,
            )

        request.state.rate_limit_execution = execution
        response = await call_next(request)
        for name, value in headers.items():
            response.headers[name] = value
        return response
