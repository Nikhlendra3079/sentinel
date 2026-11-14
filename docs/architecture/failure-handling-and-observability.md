# Failure handling and observability

## Failure policy

`SENTINEL_RATE_LIMIT_FAIL_OPEN=false` is the default (fail closed): if Redis cannot execute the rate-limit decision, the middleware returns HTTP 503 with `Retry-After: 1`. It does not misrepresent an infrastructure failure as HTTP 429.

Set `SENTINEL_RATE_LIMIT_FAIL_OPEN=true` only when application availability is more important than enforcing quotas during a Redis outage. In that mode the request proceeds after successful database-backed authentication and policy lookup. The event is logged and counted. Authentication/database failures are always fail-closed; fail-open applies only to the rate-limit Redis execution.

An invalid API key is not authenticated by the middleware; the existing `require_tenant` dependency remains responsible for returning 401 on protected routes. A valid principal is attached to `request.state` and reused by the dependency to avoid a duplicate API-key query.

## HTTP behaviour

- Allowed request: continue to the route and attach `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` plus `X-RateLimit-*` compatibility headers.
- Denied request: return 429 with a JSON detail, policy ID, algorithm, quota headers, and `Retry-After` when a finite retry time exists.
- Redis unavailable (default): return 503 with a short retry hint.
- No matching policy: continue without rate-limit headers.

Reset and retry header values are rounded up to whole seconds. Remaining is floored because the header is an integer-facing representation of potentially fractional token usage.

## Metrics and logs

`GET /metrics` exposes a small Prometheus text endpoint with counters labelled only by algorithm and outcome. Tenant IDs, API keys, policy IDs, and raw paths are intentionally excluded to avoid high-cardinality metrics and sensitive labels. Protect this endpoint at the network/ingress layer in production.

Logs never include bearer credentials. Redis failures include the algorithm but not tenant identity. A production deployment should additionally collect Redis command/script latency, Redis memory and evictions, connection-pool saturation, 429/503 rates, and request latency histograms.

## Known limitations

- Active policies are loaded from PostgreSQL on every authenticated API request. This keeps policy updates visible immediately but adds database work; a bounded cache plus explicit invalidation/version semantics is a later optimization.
- Middleware uses request cost 1.0. Weighted cost propagation from endpoint metadata is not exposed yet.
- Metrics are process-local counters; scrape every worker or replace with a Prometheus client/exporter in production.
- A Redis failover or loss of unreplicated writes can reset recent quota state. Redis Lua atomicity does not make Redis state durable or consensus-backed.
- Sliding Window Log can use substantial memory and longer scripts for high-rate policies.
