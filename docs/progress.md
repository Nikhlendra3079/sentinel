# Project progress

## Milestone 1 — Foundation

- [x] FastAPI application and lifespan
- [x] Settings via environment variables
- [x] Async SQLAlchemy engine
- [x] Async Redis client lifecycle
- [x] Tenant, API key and policy models
- [x] Initial Alembic migration
- [x] Liveness and readiness endpoints
- [x] Docker Compose for PostgreSQL and Redis
- [x] Initial liveness test

## Milestone 2 — Identity and authentication

- [x] API key generation using Python `secrets`
- [x] SHA-256 storage hash and constant-time verification
- [x] Public-prefix lookup
- [x] Tenant creation and retrieval
- [x] Tenant status management
- [x] API key issuance and listing
- [x] API key revocation
- [x] Atomic database transaction for key rotation
- [x] Bearer authentication dependency
- [x] Authenticated tenant identity endpoint
- [x] Admin bootstrap authentication
- [x] Unit tests for API-key primitives

## Historical limitations recorded at the end of M2

- API-key and tenant authentication currently queries PostgreSQL on each authenticated request; caching and revocation consistency need an explicit design.
- Admin authentication is a single bootstrap secret, not full RBAC.
- Key rotation immediately revokes the old key; no grace period is implemented.
- Tenant status changes take effect on the next database-backed authentication check.
- No rate-limiting policy enforcement exists yet.

## Next milestone (historical M2 plan)

Rate-limit policy management and the in-process algorithm interface, followed by the custom token-bucket implementation.


## Milestone 3 — Rate-limiting engine (in-process foundation)

- [x] Define framework-independent algorithm protocol
- [x] Define common rate-limit decision value object
- [x] Implement token bucket mathematics from scratch
- [x] Use monotonic time and injectable fake clock
- [x] Support fractional refill and variable request cost
- [x] Add per-key thread safety
- [x] Map database policy fields to token bucket configuration
- [x] Test refill, capacity, denial, isolation, invalid inputs and concurrency
- [x] Implement fixed-window algorithm
- [x] Implement sliding-window log algorithm
- [x] Add policy CRUD and policy-resolution precedence
- [x] Add algorithm factory/engine with policy-versioned instances
- [x] Implement shared Redis-backed atomic execution (completed in M4)

## M3.4 — Policy management and algorithm selection

- Added policy create/list/update/delete admin endpoints.
- Added exact, longest-prefix, and catch-all endpoint matching precedence.
- Enforced one active policy per tenant and endpoint pattern with a PostgreSQL partial unique index.
- Added an in-process engine that selects the algorithm from the resolved policy.
- Policy updates increment the version and create a fresh local limiter instance.
- Added policy resolver and engine tests.

## Known limitations

- All three algorithm implementations are process-local and lose state on restart.
- Per-key locks and bucket states are retained indefinitely; eviction is deferred.
- The engine is not yet integrated into the HTTP request middleware path.
- It does not yet enforce quotas consistently across multiple Uvicorn workers or machines.
- Changing a policy version resets its in-process quota; distributed policy-update semantics remain to be designed.


## M3.3 — Sliding Window Log

- Implemented rolling-window log with weighted request costs.
- Uses monotonic timestamps, per-key locks, running usage totals, pruning, and weighted retry-after calculation.
- Added deterministic and concurrent tests.
- Limitation: process-local state; distributed atomic enforcement is future work.

## Milestone 3 — Exit criteria

- [x] Three algorithm implementations share one decision contract.
- [x] Algorithm selection is independent of FastAPI route handlers.
- [x] Policy CRUD and deterministic endpoint precedence are implemented.
- [x] PostgreSQL protects active-policy pattern uniqueness.
- [x] Unit tests cover algorithm behaviour, concurrency, policy matching and engine selection.
- [x] Architecture decisions and known limitations are documented.

**M3 complete: in-process rate-limiting foundation.** Redis-backed atomic enforcement and HTTP request-path integration are explicitly deferred to M4.

## Milestone 4 — Distributed rate limiting

- [x] Define Redis key model scoped by tenant, policy, and policy version.
- [x] Use Redis Cluster hash tags for multi-key sliding-window scripts.
- [x] Implement Redis Lua Token Bucket using Redis server TIME.
- [x] Implement Redis Lua Fixed Window using Redis server TIME.
- [x] Implement weighted Redis Sorted-Set Sliding Window Log with atomic pruning and retry calculation.
- [x] Add asynchronous Redis policy execution engine and decision decoding.
- [x] Add HTTP middleware for authenticated tenant requests and policy enforcement.
- [x] Reuse middleware-authenticated tenant principal in FastAPI authentication dependency.
- [x] Return 429 with quota and Retry-After headers; distinguish Redis outage as 503.
- [x] Add configurable fail-open/fail-closed behaviour (default fail closed).
- [x] Add low-cardinality Prometheus text counters at `/metrics`.
- [x] Add unit tests for Redis engine key/response mapping and middleware outcomes.
- [x] Add opt-in real-Redis Lua concurrency integration tests.
- [x] Document Redis data model, Lua atomicity, cluster slotting, TTL, and failure semantics.

### M4 operational limitations

- Policy rows are loaded from PostgreSQL on every authenticated API request; caching and invalidation are deferred.
- Middleware uses request cost 1.0; weighted request cost is supported by scripts/engine but not yet configured per endpoint.
- `/metrics` counters are process-local and should be scraped per worker; protect the endpoint at the ingress/network layer in production.
- Redis script atomicity does not guarantee quota-state durability through failover, eviction, or data loss. Redis is configured with `noeviction` in Compose; production memory sizing and persistence/replication guarantees remain operational decisions.
- Sliding Window Log has O(n) retry calculation in the active log and can be expensive for very high request rates.
- The test environment used to author this milestone did not include `redis`, `asyncpg`, or a Redis server, and outbound package installation was unavailable. Compile checks passed; Redis integration tests are provided for execution against a real Redis instance and are not claimed as executed here.

**M4 implementation complete; live Redis/DB integration verification remains to be run in the local Docker environment.**


## Milestone 5 — Performance, resilience, and operations

- [x] Add Locust authenticated protected-endpoint workload and load-test runbook.
- [x] Add in-process and Redis microbenchmark with throughput and p50/p95/p99 latency output.
- [x] Add HTTP request duration Prometheus histogram with bounded labels.
- [x] Add configurable Uvicorn worker count to the container entrypoint.
- [x] Add opt-in cross-process quota integration tests for all three algorithms.
- [x] Add Redis key TTL integration tests.
- [x] Add Redis outage/recovery runbook for fail-open and fail-closed behaviour.
- [x] Add Redis memory/key-expiry diagnostics using SCAN and MEMORY USAGE.
- [x] Add optional Prometheus and Grafana Compose profile with provisioned dashboard.
- [x] Add cProfile workflow for in-process algorithm profiling.
- [x] Document benchmark methodology, operational limitations, and optimization process.

**M5 implementation complete.** Performance numbers must be generated on the target
machine; no universal RPS or latency claims are made. The local Grafana dashboard
uses process-local metrics and is intended for one worker. Redis state is shared
across workers; production metrics aggregation and Redis failover testing remain
deployment-specific follow-up work.
