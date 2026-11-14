# Sentinel --- Distributed Multi-Tenant API Gateway

Sentinel is a learning project for a distributed API gateway and
rate-limiting service built with Python, FastAPI, PostgreSQL and Redis.

## Current milestones

-   **M1 --- Foundation:** FastAPI, async SQLAlchemy, Redis client,
    PostgreSQL schema, Alembic and Docker Compose.
-   **M2 --- Identity:** tenant management, API-key
    issuance/revocation/rotation, API-key hashing and authentication.
-   **M3 --- Rate-limiting foundation:** Token Bucket, Fixed Window,
    Sliding Window Log, policy CRUD, endpoint matching precedence, and
    an in-process algorithm engine.
-   **M4 --- Distributed enforcement:** Redis Lua scripts, shared policy
    state, FastAPI middleware, HTTP quota headers, failure modes, and
    basic metrics.
-   **M5 --- Performance and operations:** Locust load testing,
    algorithm microbenchmarks, HTTP latency histograms, multi-process
    quota verification, Redis outage/TTL diagnostics,
    Prometheus/Grafana, and cProfile workflows.

## Quick start --- Docker Compose (recommended)

Docker Compose is the easiest way to run Sentinel on a fresh machine. It
starts the API, PostgreSQL, and Redis together, so you do not need to
install or configure PostgreSQL and Redis separately.

### Prerequisites

-   Git
-   Docker Desktop with the Docker Compose plugin

Start Docker Desktop before running the commands below.

### 1. Clone the repository

``` powershell
git clone https://github.com/Nikhlendra3079/sentinel.git
cd sentinel
```

### 2. Create your local environment file

``` powershell
Copy-Item .env.example .env
notepad .env
```

Set `SENTINEL_ADMIN_API_KEY` to a long, random development secret, then
save the file. Keep `.env` private: it is ignored by Git and must never
be committed. Use `.env.example` as the shareable template; do not put
real credentials in it.

### 3. Build and start the application

``` powershell
docker compose up --build -d
```

The Compose configuration starts the API, PostgreSQL, and Redis. The API
container runs the database migrations before starting the application.

Check container status:

``` powershell
docker compose ps
```

If the API does not start successfully, inspect its logs:

``` powershell
docker compose logs --tail 100 api
```

Follow live API logs:

``` powershell
docker compose logs -f api
```

Press `Ctrl+C` to stop following the logs; this does not stop the
containers.

### 4. Open the API

-   Interactive API documentation: http://localhost:8000/docs
-   Use the health endpoints listed in the API documentation to check
    service status.

The API is now available locally. Use the admin API workflow below to
create a tenant, issue an API key, and configure a rate-limit policy
before calling a protected endpoint.

### 5. Start optional monitoring

``` powershell
docker compose --profile monitoring up -d
```

Then open:

-   Prometheus: http://localhost:9090
-   Grafana: http://localhost:3000

Use the Grafana credentials configured by your local Compose/environment
configuration. Do not assume development credentials are suitable for a
shared or public deployment. The included dashboard is intended for a
single-worker local deployment because the lightweight metrics collector
is process-local.

### 6. Stop the application

Stop containers while preserving their persistent data:

``` powershell
docker compose down
```

To also delete Compose-managed volumes (including persisted PostgreSQL
data):

``` powershell
docker compose down -v
```

**Warning:** `docker compose down -v` is destructive. Use it only when
you intend to reset the local database and other persisted volume data.

### Docker troubleshooting

-   If `docker` is not recognized, install or update Docker Desktop,
    then open a new PowerShell window.
-   If Docker reports that its engine is unavailable, start Docker
    Desktop and wait until it has finished starting.
-   If a port is already in use, stop the other service using that port
    or change the relevant port mapping in `docker-compose.yml`.
-   If the API exits during startup, inspect `docker compose logs api`.
    Check that `.env` exists and contains the required configuration.
-   To rebuild after changing application code or dependencies, run
    `docker compose up --build -d`.

------------------------------------------------------------------------

## Requirements

-   Python 3.12+
-   Docker Desktop with Docker Compose

## Local development --- run the API with Python on Windows PowerShell

Use this route when you want to run the FastAPI process directly on
Windows for development. PostgreSQL and Redis still need to be running;
the Docker Compose quick start above can start those dependencies for
you.

``` powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `.env` and set `SENTINEL_ADMIN_API_KEY` to a long random value.
Start infrastructure:

``` powershell
docker compose up -d postgres redis
alembic upgrade head
uvicorn app.main:app --reload
```

Run tests:

``` powershell
pytest -v
```

API docs: http://localhost:8000/docs

## Milestone 2 API

All `/api/v1/admin/*` endpoints require `X-Admin-Token` matching
`SENTINEL_ADMIN_API_KEY`.

  --------------------------------------------------------------------------------------------
  Method                  Endpoint                                     Purpose
  ----------------------- -------------------------------------------- -----------------------
  POST                    `/api/v1/admin/tenants`                      Create tenant

  GET                     `/api/v1/admin/tenants/{tenant_id}`          Retrieve tenant

  PATCH                   `/api/v1/admin/tenants/{tenant_id}/status`   Change tenant status

  POST                    `/api/v1/admin/tenants/{tenant_id}/keys`     Issue API key

  GET                     `/api/v1/admin/tenants/{tenant_id}/keys`     List key metadata

  POST                    `/api/v1/admin/keys/{key_id}/revoke`         Revoke API key

  POST                    `/api/v1/admin/keys/{key_id}/rotate`         Revoke old key and
                                                                       issue replacement

  GET                     `/api/v1/me`                                 Resolve authenticated
                                                                       tenant

  GET                     `/api/v1/protected/ping`                     Protected example
                                                                       endpoint
  --------------------------------------------------------------------------------------------

## Security model

-   API keys contain a non-secret 16-hex-character public lookup prefix
    and a 256-bit random secret.
-   Only SHA-256 hashes are persisted. This is appropriate for
    high-entropy random API keys, not human passwords.
-   The original key is returned once at issuance/rotation and cannot be
    retrieved later.
-   Hashes are compared with `secrets.compare_digest`.
-   Tenant API keys and the administrator bootstrap secret are separate
    credentials.
-   Never log API keys or Authorization headers. Use TLS outside local
    development.

## Known limitations

-   Authentication performs a PostgreSQL lookup on each request. Caching
    and revocation consistency are deferred.
-   The admin secret is a bootstrap mechanism, not a complete RBAC
    system.
-   Rotation immediately revokes the old key; no grace period is
    implemented.
-   Policies are loaded from PostgreSQL on every authenticated API
    request; caching and invalidation are deferred.
-   Middleware currently charges one unit per request; weighted request
    costs are supported by the engine but not yet configurable per
    endpoint.
-   Sliding Window Log has O(n) retry calculation and can be expensive
    for high-volume policies.
-   `/metrics` counters are process-local; scrape each worker or replace
    with a shared metrics exporter in production.
-   Redis Lua execution is atomic on the executing primary, but Redis
    failover/eviction/data loss can still reset recent quota state.

## Example workflow (PowerShell)

Set the admin secret in `.env`, start the app, and create a tenant:

``` powershell
$admin = "replace-this-with-the-value-from-your-env"
$headers = @{ "X-Admin-Token" = $admin }
$tenant = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/v1/admin/tenants" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"name":"Acme Corporation"}'

$tenantId = $tenant.id
```

Issue a key. Save the `key` value securely; it is returned only once:

``` powershell
$issued = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/v1/admin/tenants/$tenantId/keys" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"name":"local-development"}'

$apiKey = $issued.key
```

Create a catch-all rate-limit policy for this tenant (five requests per
fixed 60-second window):

``` powershell
$policyBody = @{
  algorithm = "fixed_window"
  limit_count = 5
  window_seconds = 60
  endpoint_pattern = "*"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/v1/admin/tenants/$tenantId/policies" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $policyBody
```

Call the protected endpoint. The sixth request in the same fixed window
should receive HTTP 429:

``` powershell
$clientHeaders = @{ Authorization = "Bearer $apiKey" }
1..7 | ForEach-Object {
  try {
    $result = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/protected/ping" -Headers $clientHeaders
    Write-Host "Request $_ => allowed"
  } catch {
    $statusCode = [int]$_.Exception.Response.StatusCode
    Write-Host "Request $_ => HTTP $statusCode"
  }
}
```

Resolve the authenticated tenant:

``` powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/me" -Headers $clientHeaders
```

List key metadata (the plaintext key is never returned):

``` powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/admin/tenants/$tenantId/keys" -Headers $headers
```

Never paste real API keys into source code, commit them, or share
terminal output containing them.

## Milestone 3 --- In-process rate-limiting engine

The project now includes a framework-independent rate-limiting contract
and a custom, thread-safe in-process token bucket.

### Token bucket configuration

-   `capacity`: maximum stored tokens
-   `refill_rate`: tokens replenished per second
-   `cost`: token cost of an individual request (defaults to 1)

Example:

``` python
from app.limiter import TokenBucketConfig, TokenBucketLimiter

limiter = TokenBucketLimiter(
    TokenBucketConfig(capacity=100, refill_rate=100 / 60),
)

decision = limiter.consume("tenant-id:policy-id")
if decision.allowed:
    print("allow", decision.remaining)
else:
    print("reject", decision.retry_after_seconds)
```

The M3 implementation uses `time.monotonic()` and supports an injected
clock for deterministic tests. It remains available as an educational
in-process implementation; the HTTP request path now uses the
Redis-backed M4 engine for shared quotas.

### Run algorithm tests

``` powershell
pytest tests/test_token_bucket.py -v
```

### Policy mapping

The existing database policy fields map to token bucket as follows:

-   `limit_count / window_seconds` = refill tokens per second
-   `burst_capacity` = bucket capacity
-   when `burst_capacity` is null, `limit_count` is used as capacity

## Milestone 3 policy administration

All policy endpoints require the admin bootstrap header `X-Admin-Token`.

  ----------------------------------------------------------------------------------------------
  Method                  Endpoint                                       Purpose
  ----------------------- ---------------------------------------------- -----------------------
  POST                    `/api/v1/admin/tenants/{tenant_id}/policies`   Create a policy

  GET                     `/api/v1/admin/tenants/{tenant_id}/policies`   List tenant policies

  PATCH                   `/api/v1/admin/policies/{policy_id}`           Update a policy and
                                                                         increment its version

  DELETE                  `/api/v1/admin/policies/{policy_id}`           Delete a policy
  ----------------------------------------------------------------------------------------------

Endpoint patterns support `*` (fallback), `/v1/*` (segment-aware
prefix), and `/v1/users` (exact path). Resolution precedence is exact,
longest prefix, then fallback. Only one active policy per tenant and
pattern is permitted. See `docs/architecture/policy-resolution.md`.

Apply all schema migrations after updating: `alembic upgrade head`.

## Milestone 4 --- Distributed rate-limit enforcement

The M4 implementation executes the Token Bucket, Fixed Window, and
Sliding Window Log decisions in Redis Lua scripts. Each script uses
Redis server `TIME` and performs the complete read/expire/check/update
operation atomically. Redis keys are scoped by tenant, policy, and
policy version; sliding-window keys share a Redis Cluster hash tag. See
`docs/architecture/redis-data-model.md` and
`docs/architecture/redis-lua-atomicity.md`.

### Middleware behaviour

The middleware applies to authenticated bearer requests under
`/api/v1/`, excluding admin routes. It loads the tenant's active
policies, resolves exact path \> longest prefix \> catch-all, and
invokes the Redis engine. A valid principal is placed on request state
and reused by `require_tenant`.

-   Allowed: route continues with `RateLimit-Limit`,
    `RateLimit-Remaining`, `RateLimit-Reset`, and `X-RateLimit-*`
    headers.
-   Denied: HTTP 429 with `Retry-After` and a JSON response.
-   Redis unavailable: HTTP 503 by default.
-   Optional fail-open: set `SENTINEL_RATE_LIMIT_FAIL_OPEN=true` to
    allow the request through after successful authentication and policy
    lookup if only the Redis decision fails. Authentication/database
    failures always fail closed.
-   No matching policy: request continues without rate-limit headers.

`GET /metrics` exposes low-cardinality Prometheus text counters. Protect
this endpoint at the ingress/network layer in production.

### Run M4

``` powershell
docker compose up -d postgres redis
alembic upgrade head
uvicorn app.main:app --reload
```

The Compose Redis service uses a 256 MB memory ceiling and `noeviction`:
when full, writes fail instead of silently evicting live quota keys, and
the default middleware response is 503. Production deployments still
need memory sizing, persistence, replication, and failover policies
appropriate to their quota correctness requirements. No database schema
migration was required for M4.

### Test M4

``` powershell
pytest -v
```

The real Redis Lua concurrency tests are opt-in. Set a dedicated Redis
test database URL first (the example uses logical database 15):

``` powershell
$env:SENTINEL_TEST_REDIS_URL = "redis://localhost:6379/15"
pytest tests/integration/test_redis_lua_integration.py -v
```

The integration tests use random tenant/policy IDs and do not flush the
database. They issue 50 concurrent requests against each algorithm and
assert exactly 10 admissions for a 10-request initial quota.

### Operational caveats

-   Lua scripts serialize decisions atomically on one Redis primary;
    this is not a consensus or durability guarantee across failover.
-   Policy rows are currently queried from PostgreSQL on every
    authenticated request.
-   Middleware request cost is fixed at 1.0.
-   Sliding Window Log stores each admitted event and can consume
    substantial memory for high-rate/long-window policies.
-   Metrics are process-local.
-   Default Redis failure behaviour is fail-closed (503), not 429. See
    `docs/architecture/failure-handling-and-observability.md`.

## Milestone 5 --- Performance, resilience, and operations

M5 adds repeatable measurement and operational validation tools. It
intentionally does not publish fabricated throughput targets: benchmark
on the machine and deployment you intend to evaluate.

Install Locust with the development dependencies:

``` powershell
pip install -e ".[dev]"
```

See `docs/architecture/milestone-5-performance-and-operations.md` for
all eight M5 workstreams and complete PowerShell runbooks.

Quick start:

``` powershell
# Load test (create a tenant/key/policy first)
$env:SENTINEL_TEST_API_KEY = "<issued-key>"
locust -f locustfile.py --host http://localhost:8000

# Algorithm microbenchmark
python scripts/benchmark_algorithms.py --iterations 20000 --concurrency 8

# Redis benchmark
python scripts/benchmark_algorithms.py --iterations 5000 --concurrency 16 `
  --redis-url redis://localhost:6379/15

# Redis memory / TTL diagnostics
python scripts/redis_diagnostics.py --redis-url redis://localhost:6379/15

# CPU profile
python scripts/profile_in_process.py --iterations 100000 --algorithm sliding_window

# Optional Prometheus + Grafana
docker compose --profile monitoring up -d
```

Cross-process and TTL integration tests use a dedicated Redis test
database:

``` powershell
$env:SENTINEL_TEST_REDIS_URL = "redis://localhost:6379/15"
pytest tests/integration/test_redis_multi_process.py -v
pytest tests/integration/test_redis_key_ttl.py -v
```

**Metrics limitation:** the included lightweight Prometheus collector is
process-local. The provided Grafana dashboard is intended for a
single-worker local deployment. Redis quota enforcement itself is shared
across Uvicorn workers, and a cross-process integration test verifies
this property. For aggregated production metrics across multiple
workers, adopt Prometheus multiprocess mode or an external aggregation
strategy.
