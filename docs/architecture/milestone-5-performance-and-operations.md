# M5 — Performance, resilience, and operational validation

M5 does not claim a universal requests-per-second target. It adds repeatable
experiments, metrics, dashboards, operational runbooks, and profiling tools so
the operator can measure a particular machine and deployment.

## 1. Load testing with Locust

Install the optional load-test dependency:

```powershell
pip install -e ".[dev]"
```

Create a tenant, issue an API key, and configure an active policy for
`/api/v1/protected/ping`. Set the key without committing it:

```powershell
$env:SENTINEL_TEST_API_KEY = "<issued-key>"
locust -f locustfile.py --host http://localhost:8000
```

Open http://localhost:8089. Start with 10 users and ramp gradually. Record
users, spawn rate, run duration, request count, failures, and response-time
percentiles. The Locust workload treats HTTP 429 as an expected rate-limit
outcome, but treats 503 and unexpected responses as failures.

Headless example:

```powershell
New-Item -ItemType Directory -Force artifacts | Out-Null
locust -f locustfile.py --host http://localhost:8000 `
  --headless -u 25 -r 5 -t 2m `
  --csv artifacts/locust-baseline
```

Do not benchmark against a production tenant or a shared Redis database.

## 2. Algorithm microbenchmarks

Run local implementations first:

```powershell
python scripts/benchmark_algorithms.py --iterations 20000 --concurrency 8
```

Include Redis-backed execution:

```powershell
python scripts/benchmark_algorithms.py --iterations 5000 --concurrency 16 `
  --redis-url redis://localhost:6379/15 `
  --output artifacts/redis-benchmark.json
```

The report includes throughput, p50/p95/p99 and mean operation latency,
admission count, and errors. Local tests use one hot key and therefore include
Python lock contention. Redis timings include client scheduling, network
round-trip, Redis execution, and Lua runtime. They are not directly comparable
to HTTP request latency.

For fair comparisons:
- use an otherwise idle machine;
- run each case several times and compare medians;
- keep iterations, concurrency, Redis location, and policy size constant;
- separate warm-up from measured runs when making formal claims;
- report the exact hardware, Python, Redis and OS versions;
- do not extrapolate a local microbenchmark into a production capacity promise.

## 3. Latency percentiles

The benchmark calculates nearest-rank p50, p95 and p99. The application
exports a Prometheus histogram `sentinel_http_request_duration_seconds` with
bounded labels `method` and `status_class`. The histogram is cumulative as
required by Prometheus.

PromQL examples:

```promql
sum(rate(sentinel_http_requests_total[1m]))
```

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(sentinel_http_request_duration_seconds_bucket[5m]))
)
```

```promql
sum by (status_class) (rate(sentinel_http_requests_total[1m]))
```

These histograms measure middleware-observed HTTP request duration. They are
not a pure Redis-Lua latency metric. The benchmark script measures engine
operation latency separately.

## 4. Multiple Uvicorn workers

The container command supports `SENTINEL_UVICORN_WORKERS`:

```powershell
$env:SENTINEL_UVICORN_WORKERS = "4"
docker compose up -d --build api
docker compose logs -f api
```

Each worker is a separate process with its own Python heap, SQLAlchemy pool,
Redis connection pool, and process-local metrics collector. Rate-limit state
is shared because every worker executes the same Redis Lua scripts against the
same Redis service.

The cross-process integration test is opt-in:

```powershell
$env:SENTINEL_TEST_REDIS_URL = "redis://localhost:6379/15"
pytest tests/integration/test_redis_multi_process.py -v
```

It starts four independent Python processes and verifies that their combined
admissions do not exceed the shared quota.

Capacity planning note: SQLAlchemy pool limits are per worker. Four workers
with `pool_size=10` and `max_overflow=20` can theoretically open up to 120
database connections. Tune worker count and pool limits together.

Metrics caveat: this project's lightweight collector is process-local. A
single `/metrics` scrape behind a multi-worker Uvicorn socket reaches one
worker, not a merged view of every worker. Use one worker for the included
single-target Grafana dashboard, or adopt Prometheus multiprocess mode /
per-worker scrape aggregation before relying on multi-worker aggregate metrics.

## 5. Redis outage and recovery experiments

The middleware defaults to fail-closed: if Redis cannot make a rate-limit
decision, an authenticated request receives HTTP 503. Fail-open is an explicit
availability-over-enforcement choice.

With Docker Compose:

```powershell
docker compose pause redis
```

Send an authenticated request to `/api/v1/protected/ping`. With the default
configuration, expect 503 and `Retry-After: 1`. Then restore Redis:

```powershell
docker compose unpause redis
docker compose exec redis redis-cli PING
```

After Redis responds, requests should return to normal enforcement. The
client timeout is bounded by the Redis socket timeout configured at startup.

To test fail-open, set this in `.env`:

```env
SENTINEL_RATE_LIMIT_FAIL_OPEN=true
```

Recreate the API service so it reloads settings:

```powershell
docker compose up -d --force-recreate api
```

Repeat the Redis pause test. Once authentication and policy lookup have
succeeded, Redis failure should allow the request through. Restore Redis
immediately after the experiment.

Important: fail-open can permit unmetered traffic during an outage. It must
be selected based on the protected resource's risk, not merely convenience.
Database authentication and policy lookup failures remain fail-closed.

## 6. Redis memory and key-expiry analysis

All `sentinel:rl:*` state keys are intended to have expiry. Inspect aggregate
memory and TTL data without printing tenant identifiers:

```powershell
python scripts/redis_diagnostics.py --redis-url redis://localhost:6379/15
```

The script uses SCAN, not KEYS, and reports key count, estimated key memory,
keys without expiry, TTL range, and Redis memory information. Run it against
the same Redis database used by the test or benchmark.

The opt-in TTL integration tests are:

```powershell
pytest tests/integration/test_redis_key_ttl.py -v
```

Sliding Window Log has state proportional to admitted requests in the active
window. A high-rate, long-window policy can therefore consume materially more
memory than Token Bucket or Fixed Window. Memory sizing must be based on
measured event volume and per-entry overhead, not just payload bytes.

Redis uses `noeviction` in local Compose. This avoids silently evicting quota
state but means writes fail when the configured memory ceiling is reached;
the default middleware behaviour is then 503.

## 7. Prometheus and Grafana

Start the optional monitoring profile:

```powershell
docker compose --profile monitoring up -d
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- Local Grafana credentials: `admin` / `sentinel-local-only`

The datasource and Sentinel overview dashboard are provisioned from
`monitoring/grafana`. Change `GRAFANA_ADMIN_PASSWORD` in `.env` before using
this beyond a local machine. Do not expose Grafana or `/metrics` publicly
without authentication and network controls.

The dashboard covers HTTP request rate, rate-limit decisions, p95/p99 latency,
HTTP status classes, and allow/deny rates.

## 8. Profiling and optimization

Profile a selected in-process algorithm:

```powershell
python scripts/profile_in_process.py --iterations 100000 `
  --algorithm sliding_window
```

The script writes `artifacts/sentinel-profile.prof` and prints cumulative
function costs. Open the profile with:

```powershell
python -m pstats artifacts/sentinel-profile.prof
```

Profile before optimizing. Likely cost centres differ by workload:
- Python lock acquisition and dictionary lookups for local algorithms;
- Redis round-trip and connection-pool queueing for distributed enforcement;
- Lua sorted-set scans and per-event hash lookups for Sliding Window Log;
- PostgreSQL authentication and policy reads on every authenticated request;
- ASGI middleware and response serialization overhead.

Do not optimize based on a single run. Make one change at a time, rerun the
same benchmark, compare p95/p99 and throughput, and retain correctness tests.

## M5 exit criteria

- [x] Repeatable Locust workload and documented baseline procedure.
- [x] Algorithm microbenchmark with p50/p95/p99 and throughput output.
- [x] HTTP latency histogram and Prometheus queries.
- [x] Configurable multi-worker container deployment.
- [x] Cross-process Redis quota integration test.
- [x] Redis outage/recovery runbook and explicit fail-open/closed trade-offs.
- [x] Redis memory and TTL diagnostic script plus TTL integration test.
- [x] Prometheus/Grafana provisioning and dashboard.
- [x] cProfile workflow and optimization guidance.

## What this milestone does not claim

No benchmark numbers are fabricated or embedded as expected performance.
Run the included tools on the target machine and preserve their JSON/CSV
outputs as project evidence. Compose uses a single Redis primary; it does not
simulate Sentinel/Cluster failover, network partitions, persistence loss, or
replica promotion. The included metrics collector is process-local and the
dashboard is intended for a single-worker local observability setup.
