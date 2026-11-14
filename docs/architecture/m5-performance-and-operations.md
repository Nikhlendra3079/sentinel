# M5 — Performance, resilience, and operations

## Scope

M5 does not change the quota algorithm semantics. It adds repeatable tools to measure the existing Redis-backed request path, validate shared quota state across workers, inspect Redis state, and operate the service during dependency failures.

## 1. Load testing

`locustfile.py` uses a real issued tenant API key against `/api/v1/protected/ping`. HTTP 200 and 429 are both successful workload outcomes: a 429 is the expected result when the configured policy is exhausted. HTTP 503 and unexpected status codes are workload failures.

Start with a low user count and increase gradually. Keep the policy, request distribution, Redis topology, machine, and run duration constant when comparing builds.

## 2. Algorithm benchmark

`scripts/benchmark_redis.py` directly invokes the production `RedisRateLimitEngine` for each algorithm. It records per-operation wall-clock latency and reports p50/p95/p99, mean, max, throughput, and admission count.

This measures the complete client-side decision call (Python scheduling + Redis connection/RTT + script execution + response decoding), not pure Lua execution time. It creates random tenant and policy IDs and does not flush the selected Redis database.

Run against an isolated Redis database and an otherwise idle machine. Sliding Window Log work grows with active events, so run multiple request/window profiles.

## 3. Latency and failure metrics

The middleware measures only the Redis rate-limit decision duration, excluding PostgreSQL authentication/policy lookup and downstream route execution. This isolates the rate-limit engine path.

Metrics use only bounded labels: algorithm, outcome, dependency, and failure mode. Do not add customer identifiers or raw paths.

## 4. Multi-worker semantics

Each Uvicorn worker has independent Python memory, but every worker uses the same Redis keys. Therefore, quota correctness must not depend on Python locks or in-process state.

Compose starts four Uvicorn workers by default. The Prometheus multiprocess directory is cleared once in the container entrypoint before Uvicorn starts; each worker writes metrics into the shared directory, and the endpoint aggregates them.

Use `scripts/verify_multiworker.py` against a fresh fixed-window quota. A result of 10 HTTP 200 and 40 HTTP 429 for 50 simultaneous requests validates that the tested HTTP path shares the Redis quota across workers.

## 5. Failure injection and recovery

### Redis unavailable

Stop Redis while keeping API workers running. With fail-closed enabled, authenticated requests with a matching policy should return 503 and `Retry-After: 1`. Restart Redis and verify readiness plus successful requests.

### Fail-open

Enable `SENTINEL_RATE_LIMIT_FAIL_OPEN=true` and recreate API workers. During Redis outage, authenticated requests should continue after PostgreSQL authentication and policy resolution. This is a quota bypass by design, not a degraded enforcement guarantee. Restore fail-closed after the experiment.

### Recovery caveat

After Redis restarts, existing quota state may survive or be lost depending on persistence and replication. Do not assume a restarted Redis primary preserves every recent script write. Validate the chosen AOF fsync, replication, and failover configuration for the deployment's consistency requirements.

## 6. Memory and TTL analysis

`scripts/redis_diagnostics.py` scans a bounded sample of `sentinel:rl:*` keys and reports type, PTTL, MEMORY USAGE, and global Redis memory information.

Expected state:
- Token Bucket: one hash with TTL long enough that expiry occurs only after the bucket would have refilled.
- Fixed Window: one hash with TTL shortly after the current fixed window ends.
- Sliding Window Log: sorted set, cost hash, usage value, and clock guard with TTLs.

A key with PTTL `-1` has no expiry and deserves investigation. PTTL `-2` means it disappeared between scan and inspection. Sampled per-key memory does not include all allocator, fragmentation, replication, or shared overhead.

## 7. Prometheus and Grafana

The optional Compose monitoring profile starts Prometheus and Grafana. Prometheus scrapes `/metrics` every five seconds. The provisioned dashboard includes decision throughput by algorithm/outcome, p95 decision latency, Redis dependency failure rate, and denied-request ratio.

The dashboard is a starting point. Add host/container CPU, memory, network, Redis command latency, connected clients, rejected connections, evictions, and AOF/replication health from infrastructure exporters in a production deployment.

## 8. Profiling and optimization

`scripts/profile_inprocess.py` profiles Python-side Token Bucket overhead with cProfile. It is useful for identifying Python lock/dictionary/clock costs, but it does not profile Redis or the FastAPI middleware.

For the complete path, profile under a reproducible Locust workload and compare:
- API p50/p95/p99,
- Redis decision p50/p95/p99,
- PostgreSQL query latency,
- Redis `INFO commandstats` and `INFO latencystats`,
- CPU and memory per process.

Likely cost centres already visible in the architecture:
1. PostgreSQL API-key authentication and policy reads on every request.
2. Redis network round trips and connection-pool contention.
3. Sliding Window Log pruning and retry calculation proportional to active events.
4. BaseHTTPMiddleware and response wrapping overhead.

Do not add policy caching before designing bounded staleness, key revocation, tenant disablement, and policy update invalidation semantics. Do not optimize from a single benchmark run.

## Operational acceptance checklist

- [ ] Locust run completes with no unexpected 5xx responses.
- [ ] Redis benchmark records p50/p95/p99 for all algorithms.
- [ ] Four-worker quota test admits exactly the configured number.
- [ ] Redis outage returns 503 in fail-closed mode.
- [ ] Redis outage permits requests in explicit fail-open mode.
- [ ] Redis recovery restores normal decisions.
- [ ] Rate-limit keys have positive TTLs.
- [ ] Grafana shows counters, latency histograms, and failures.
- [ ] cProfile output is retained with the benchmark environment.
