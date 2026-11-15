# Sentinel: From Basic Python to a Distributed Multi-Tenant API Gateway

*A beginner-friendly, implementation-oriented engineering guide*

> **Who this guide is for:** Someone who knows Python fundamentals, can
> write functions and classes, and wants to understand how a real
> backend system is assembled.
>
> **What this guide is for:** Explaining the concepts, architecture,
> request lifecycle, implementation sequence, testing strategy,
> operational behaviour, and trade-offs behind Sentinel.
>
> **Important scope note:** This guide explains the Sentinel design and
> the implementation evidence documented in the project's README and
> development notes. It is not a substitute for the source code. Where
> exact source-level details are not established by those materials, the
> guide identifies the design intent rather than inventing
> implementation details.

------------------------------------------------------------------------

# Part I --- Understand the problem before the code

## 1. What is Sentinel?

Sentinel is a multi-tenant API rate-limiting service built with:

-   Python
-   FastAPI
-   PostgreSQL
-   SQLAlchemy's asynchronous ORM
-   Redis
-   Redis Lua scripts
-   Alembic
-   Docker Compose
-   Prometheus
-   Grafana
-   Locust
-   pytest

Its central responsibility is to decide whether a request should be
allowed to continue or rejected because the caller has exceeded a
configured usage limit.

Imagine a company runs an API:

``` text
GET /api/products
GET /api/orders
POST /api/orders
GET /api/users
```

The company has different customers:

-   Free customers can make 100 requests per minute.
-   Pro customers can make 1,000 requests per minute.
-   Enterprise customers can make 10,000 requests per minute.

Without rate limiting, one customer could send a huge number of requests
and consume resources needed by everyone else.

Sentinel stores customer identity and policy configuration in
PostgreSQL, then makes fast, shared quota decisions using Redis.

## 2. What does rate limiting mean?

Rate limiting is a rule that restricts how often an identity can perform
an operation during a period of time.

For example:

``` text
Limit: 5 requests
Window: 60 seconds
```

A caller makes requests:

    Request Result
  --------- ----------
          1 Allowed
          2 Allowed
          3 Allowed
          4 Allowed
          5 Allowed
          6 Rejected
          7 Rejected

When the relevant quota becomes available again, requests can be
admitted.

The server commonly communicates a rejected request with HTTP
`429 Too Many Requests`.

A dependency failure is different. If Sentinel cannot contact Redis and
cannot make a quota decision under fail-closed mode, it returns HTTP
`503 Service Unavailable`, not 429.

## 3. Why not just use a Python dictionary?

A beginner might implement a limiter like this:

``` python
request_counts = {}

def allow_request(tenant_id):
    request_counts[tenant_id] = request_counts.get(tenant_id, 0) + 1
    return request_counts[tenant_id] <= 5
```

This is a useful first exercise, but it has serious limitations:

1.  The dictionary disappears when the process restarts.
2.  Each API worker has its own dictionary.
3.  Multiple application instances do not share the same state.
4.  Concurrent operations can race unless access is synchronized.
5.  The dictionary has no proper expiration or memory-management
    strategy.

Suppose the application has four workers:

``` text
Worker 1: customer has used 4 requests
Worker 2: customer has used 4 requests
Worker 3: customer has used 4 requests
Worker 4: customer has used 4 requests
```

If each worker independently allows five requests, the customer may
receive more than five requests in total.

Sentinel therefore separates responsibilities:

-   PostgreSQL stores durable identity and policy configuration.
-   Redis stores short-lived, shared rate-limit state.
-   FastAPI handles HTTP requests and application orchestration.

## 4. What does multi-tenant mean?

A tenant is an identity whose data and usage are logically separated
from other tenants.

For Sentinel's current implementation, think of a tenant as a customer
account belonging to an application using the service.

Example:

``` text
Sentinel
  |
  +-- Tenant A
  |     +-- API key A1
  |     +-- API key A2
  |     +-- Policy: 100 requests/minute
  |
  +-- Tenant B
        +-- API key B1
        +-- Policy: 1,000 requests/minute
```

Tenant A must not consume Tenant B's quota.

Sentinel scopes its Redis rate-limit keys by tenant, policy, and policy
version.

**Current scope limitation:** The implementation documented here has
tenants, keys, and policies. It does not yet implement a separate
organization/account layer for multiple companies using one hosted
Sentinel SaaS product. That would be a later product architecture
extension.

------------------------------------------------------------------------

# Part II --- Prerequisites: what you need to understand

You do not need to be an expert in every technology before starting.
Learn the concepts in the order below.

## 5. Python fundamentals

You should understand:

-   Variables and data types.
-   Functions and return values.
-   Classes and objects.
-   Exceptions and `try`/`except`.
-   Modules and packages.
-   Lists, dictionaries, sets, and tuples.
-   Type hints.
-   Context managers (`with`).
-   Virtual environments and package installation.

Example:

``` python
class Tenant:
    def __init__(self, tenant_id: str, name: str):
        self.tenant_id = tenant_id
        self.name = name

    def describe(self) -> str:
        return f"{self.name} ({self.tenant_id})"
```

Why this matters: Sentinel uses Python modules, classes, schemas,
service functions, and context managers throughout the application.

## 6. HTTP and REST APIs

Understand the following:

-   Client and server.
-   Request and response.
-   HTTP methods: GET, POST, PATCH, DELETE.
-   Headers.
-   JSON request bodies.
-   HTTP status codes.
-   Authentication headers.
-   REST-style resource endpoints.

Example request:

``` http
GET /api/v1/protected/ping HTTP/1.1
Host: localhost:8000
Authorization: Bearer <tenant-api-key>
```

The server responds with an HTTP status and a response body.

Important status codes:

    Status Meaning in this project
  -------- -------------------------------------------------------------
       200 Request succeeded
       401 Authentication failed
       403 Operation is forbidden, depending on endpoint rules
       429 Rate limit exceeded
       500 Unexpected application error
       503 Required dependency unavailable under fail-closed behaviour

## 7. What is an API framework?

A framework handles the repetitive work of receiving requests, parsing
inputs, calling application code, and constructing responses.

FastAPI lets you write:

``` python
from fastapi import FastAPI

app = FastAPI()

@app.get("/health/live")
async def live():
    return {"status": "alive"}
```

FastAPI receives an HTTP request, calls `live`, serializes its return
value to JSON, and sends a response.

## 8. What is asynchronous Python?

A synchronous function runs until it returns.

An asynchronous function can pause while waiting for I/O, allowing the
event loop to work on other tasks.

``` python
import asyncio

async def fetch_something():
    await asyncio.sleep(1)
    return "finished"
```

Important vocabulary:

-   `async def`: defines a coroutine function.
-   `await`: waits for an awaitable operation.
-   Event loop: schedules asynchronous work.
-   I/O-bound work: waiting for a database, network, or file operation.
-   Concurrency: overlapping progress of multiple operations.

Sentinel uses asynchronous database and Redis operations because network
I/O is central to its request path.

**Do not confuse async with automatic parallel CPU execution.** Async is
especially useful for handling many operations that spend time waiting
on I/O.

## 9. Databases and SQL

You should know:

-   Tables, rows, columns.
-   Primary keys.
-   Foreign keys.
-   Unique constraints.
-   Indexes.
-   Transactions.
-   SELECT, INSERT, UPDATE, DELETE.
-   One-to-many relationships.

A simplified Sentinel data model looks like:

``` text
Tenant
  |
  +---- API Keys
  |
  +---- Rate Limit Policies
```

PostgreSQL stores durable records such as tenants, API-key hashes, and
policies.

## 10. Redis fundamentals

Redis is an in-memory data store.

It supports data structures such as:

-   Strings.
-   Hashes.
-   Lists.
-   Sets.
-   Sorted sets.

For rate limiting, Redis is useful because it offers fast operations,
expiration, and atomic scripting.

A simple Redis counter example:

``` text
INCR request-count
EXPIRE request-count 60
```

But a real rate-limit decision often requires several related
operations. Executing those as separate commands can create race
conditions. Sentinel uses Lua scripts to make the decision atomic.

## 11. Docker fundamentals

Docker packages an application or service into a container.

Docker Compose defines multiple related services in one configuration.

Sentinel's local environment contains services such as:

``` text
API container
PostgreSQL container
Redis container
Prometheus container
Grafana container
```

The containers communicate over a Compose network.

Inside the API container, PostgreSQL is addressed by its service
hostname, `postgres`, and Redis by `redis`. `localhost` inside a
container means that container itself.

## 12. Git and testing

Learn:

-   `git status`
-   `git add`
-   `git commit`
-   `git diff`
-   Unit tests.
-   Integration tests.
-   Assertions.
-   Test fixtures.

A project is not complete just because the application starts. Tests
establish whether expected behaviour holds under controlled conditions.

------------------------------------------------------------------------

# Part III --- Understand the architecture

## 13. The three main responsibilities

Sentinel separates its responsibilities across three major components.

### PostgreSQL: durable configuration

PostgreSQL stores information that should survive an application
restart:

-   Tenant records.
-   API-key metadata and hashes.
-   Tenant status.
-   Rate-limit policies.
-   Policy versions.

It is not used as the high-frequency counter store in the rate-limit
decision path.

### Redis: shared quota state

Redis stores the state required to decide whether a request is allowed.

Examples:

-   Current token count.
-   Current fixed-window count.
-   Timestamps of admitted sliding-window events.
-   Expiration metadata.

Redis state is shared by multiple API workers.

### FastAPI: request orchestration

FastAPI receives requests and runs the application logic.

It is responsible for:

-   HTTP endpoints.
-   Request validation.
-   Middleware.
-   Authentication orchestration.
-   Policy resolution.
-   Calling the Redis limiter.
-   Returning HTTP responses.

## 14. Architecture diagram

``` mermaid
flowchart TD
    Client[API Client] --> Middleware[FastAPI Rate Limit Middleware]
    Middleware --> Auth[Authenticate API Key]
    Auth --> PG[(PostgreSQL)]
    Auth --> Policy[Load and Resolve Policy]
    Policy --> PG
    Policy --> Engine[Redis Rate Limit Engine]
    Engine --> Lua[Algorithm Lua Script]
    Lua --> Redis[(Redis)]
    Redis --> Decision{Allowed?}
    Decision -->|Yes| Endpoint[Protected Endpoint]
    Decision -->|No| Rejected[HTTP 429]
    Endpoint --> Response[HTTP Response]
    Rejected --> Response
```

## 15. A complete request, step by step

Suppose a customer sends:

``` http
GET /api/v1/protected/ping
Authorization: Bearer <api-key>
```

### Step 1: FastAPI receives the request

The ASGI server receives the HTTP request and passes it through the
application stack.

### Step 2: Middleware checks eligibility

The rate-limit middleware checks whether the path is under `/api/v1/`.

Admin paths are excluded.

If the request is not eligible, the middleware passes it onward.

### Step 3: Extract the API-key prefix

The middleware extracts a public lookup prefix from the bearer key.

The prefix helps locate a candidate API-key record without storing
plaintext keys.

### Step 4: Authenticate against PostgreSQL

The authentication service checks the candidate key and associated
tenant.

The key must be valid and the tenant must be active.

The database stores a hash, not the original plaintext API key.

### Step 5: Load active policies

The middleware retrieves active policies belonging to the authenticated
tenant.

### Step 6: Resolve the best policy

The policy resolver selects the most specific matching policy:

1.  Exact path.
2.  Longest matching prefix.
3.  Catch-all fallback.

If no policy matches, the request continues without a rate-limit
decision.

### Step 7: Call Redis

The middleware calls the Redis-backed rate-limit engine with:

-   Tenant ID.
-   Resolved policy.
-   Request cost (currently 1.0).

### Step 8: Execute the Lua script

The script performs the relevant quota-state operations atomically on
Redis.

### Step 9: Decide

If allowed, the request proceeds.

If denied, Sentinel returns HTTP 429.

If Redis fails and fail-closed mode is active, Sentinel returns HTTP
503.

### Step 10: Return headers

An allowed request receives rate-limit information in response headers,
including:

-   `RateLimit-Limit`
-   `RateLimit-Remaining`
-   `RateLimit-Reset`
-   `X-RateLimit-*`

The authenticated principal is stored on request state and reused by the
endpoint dependency, avoiding a second authentication lookup.

## 16. Why authenticate before rate limiting?

A quota must be associated with an identity.

Without authentication, Sentinel would not know which tenant's quota to
consume.

The authentication step establishes:

``` text
Presented API key
       |
       v
API-key record
       |
       v
Tenant identity
       |
       v
Tenant's active policies
       |
       v
Quota decision
```

This also prevents a caller from selecting another tenant's quota simply
by supplying an arbitrary tenant ID.

## 17. Why PostgreSQL and Redis are both necessary

A useful way to think about this distinction:

  Question                                               System
  ------------------------------------------------------ ------------
  Who is this tenant?                                    PostgreSQL
  Is this API key valid?                                 PostgreSQL
  What is this tenant's policy?                          PostgreSQL
  How many requests have been admitted in this window?   Redis
  Can this request be admitted atomically?               Redis Lua

PostgreSQL is the durable configuration store. Redis is the shared, fast
quota-state store.

------------------------------------------------------------------------

# Part IV --- Rate-limiting algorithms

## 18. Token Bucket

### The idea

Imagine a bucket containing tokens.

-   The bucket has a maximum capacity.
-   Tokens refill at a fixed rate.
-   Every request consumes tokens.
-   If there are insufficient tokens, the request is rejected.

Example:

``` text
Capacity: 10 tokens
Refill rate: 1 token per second
Request cost: 1 token
```

If the bucket is full, ten requests can be admitted immediately.

After those ten requests, the caller must wait for tokens to refill.

### Mathematical model

Let:

-   \(C\) = bucket capacity.
-   \(r\) = refill rate in tokens per second.
-   \(t\) = current time.
-   (t_0) = previous update time.
-   (T_0) = previous token count.

Then:

\[ T = `\min`{=tex}(C, T_0 + (t-t_0)r) \]

A request with cost (q) is allowed if:

\[ T `\geq `{=tex}q \]

After an allowed request:

\[ T\_{`\text{new}`{=tex}} = T-q \]

### Why use it?

Token Bucket allows bursts while controlling the long-term average rate.

### Sentinel mapping

The documented policy mapping is:

\[ r = `\frac{\text{limit\_count}}{\text{window\_seconds}}`{=tex} \]

The bucket capacity is `burst_capacity`, or `limit_count` when burst
capacity is null.

### Exercise

Implement a standalone token bucket in Python before looking at the
Redis implementation.

Test:

1.  An initially full bucket.
2.  A request that consumes the final token.
3.  A rejected request when empty.
4.  Refill after time passes.
5.  A bucket that never exceeds capacity.

Use an injectable clock so tests do not need to sleep.

## 19. Fixed Window

### The idea

Divide time into fixed intervals.

Example:

``` text
Window: 60 seconds
Limit: 100 requests
```

A counter tracks requests in the current window.

When the next window begins, the counter starts again.

### Window calculation

For a window size (W) and current time (t):

\[ `\text{window\_id}`{=tex} =
`\left`{=tex}`\lfloor `{=tex}`\frac{t}{W}`{=tex}
`\right`{=tex}`\rfloor`{=tex} \]

The counter is associated with that window.

### The boundary problem

Suppose a limit is 100 requests per minute.

A caller sends 100 requests just before a minute boundary and another
100 immediately after it.

The caller could send close to 200 requests in a very short period.

This is the fixed-window boundary burst problem.

### Why use it?

It is straightforward, memory-efficient, and easy to reason about.

### Exercise

Implement a counter keyed by tenant and window ID. Test that the count
resets when the window changes.

## 20. Sliding Window Log

### The idea

Instead of counting requests in a fixed bucket, store the timestamps of
admitted requests.

For each new request:

1.  Determine the current time.
2.  Remove events older than the rolling window.
3.  Count the remaining events.
4.  Allow the request if the count is below the limit.
5.  If allowed, record the current timestamp.

Example:

``` text
Limit: 3 requests
Window: 10 seconds

Stored events:
t=2
t=5
t=8

At t=9:
3 events are still within the window.
Reject the next request.
```

At a later time, old events expire from the active window.

### Why use it?

It provides a more precise rolling-window limit than Fixed Window.

### Trade-off

It stores individual events. Memory use and request work grow with the
number of active events.

The documented implementation has O(n) retry calculation. Sliding Window
Log is therefore not automatically the best choice for every workload.

### Exercise

Implement a deque of timestamps for one key. Add tests for:

-   Events inside the window.
-   Events exactly at the expiration boundary.
-   Multiple expired events.
-   Rejection at the limit.
-   Retry time calculation.

## 21. Comparing the algorithms

  -----------------------------------------------------------------------
  Property          Token Bucket      Fixed Window      Sliding Window
                                                        Log
  ----------------- ----------------- ----------------- -----------------
  Allows bursts     Yes, up to        Can burst at      Limited by
                    capacity          boundaries        rolling-window
                                                        count

  State             Token count and   Counter and       Event timestamps
                    time              window            

  Memory            Low               Low               Higher

  Boundary burst    No fixed-window   Yes               Avoids
  issue             boundary                            fixed-window
                                                        boundary
                                                        behaviour

  Complexity        Moderate          Low               Higher
  -----------------------------------------------------------------------

There is no universally best algorithm. Choose based on the product's
traffic shape, fairness requirements, memory budget, and precision
requirements.

------------------------------------------------------------------------

# Part V --- Why Redis Lua matters

## 22. The race condition without atomic execution

Imagine the quota is 9 out of 10.

Two requests arrive at almost exactly the same time.

Without an atomic operation:

``` text
Request A reads count = 9
Request B reads count = 9

Request A decides allowed
Request B decides allowed

Request A writes count = 10
Request B writes count = 10
```

Both requests were admitted, even though only one slot remained.

This is a race condition.

## 23. What does atomic mean?

An operation is atomic when it behaves as one indivisible operation from
the perspective of competing operations.

Redis executes a Lua script without interleaving another Redis command
in the middle of that script.

The script can therefore:

1.  Read quota state.
2.  Calculate the decision.
3.  Update state.
4.  Set expiration.
5.  Return the decision.

The sequence is atomic on the Redis primary executing it.

This does not guarantee that quota state survives every Redis failover
or data-loss scenario.

## 24. Why use Redis server time?

If each API worker uses its own system clock, clocks may differ.

For time-window algorithms, clock disagreement can lead to inconsistent
decisions.

The Sentinel Lua scripts use Redis server `TIME`.

This gives the scripts a common time source for the quota decision.

## 25. Why include policy version in Redis keys?

Suppose a tenant has a policy:

``` text
100 requests per minute
```

The company changes it to:

``` text
20 requests per minute
```

If the new policy reuses the old quota state without considering the
change, behaviour can be surprising.

Sentinel scopes Redis keys by:

-   Tenant.
-   Policy.
-   Policy version.

This isolates quota state associated with different policy versions.

## 26. Redis Cluster hash tags

Redis Cluster distributes keys across hash slots.

Some operations involving multiple keys require those keys to be placed
in the same slot.

A hash tag is a substring inside braces in a Redis key. Redis uses that
substring to determine the hash slot.

Sentinel's Sliding Window Log keys use a shared hash tag for the related
keys.

This is a Redis Cluster compatibility consideration, not a guarantee
that the project has been deployed and tested on a Redis Cluster.

------------------------------------------------------------------------

# Part VI --- Reconstruct Sentinel milestone by milestone

The following is the recommended build order. It teaches the
architecture progressively instead of starting with distributed rate
limiting.

## 27. M1 --- Build the application foundation

### Goal

Create a FastAPI application that can communicate with PostgreSQL and
Redis.

### Concepts

-   Python package structure.
-   FastAPI application lifecycle.
-   Environment configuration.
-   Database engine.
-   SQLAlchemy async sessions.
-   Alembic migrations.
-   Docker Compose.
-   Health endpoints.

### Suggested implementation order

1.  Create a Python project and virtual environment.
2.  Install FastAPI, Uvicorn, SQLAlchemy, asyncpg, Redis client,
    Pydantic Settings, Alembic, and pytest.
3.  Create the FastAPI application.
4.  Add a liveness endpoint.
5.  Add PostgreSQL to Docker Compose.
6.  Add Redis to Docker Compose.
7.  Configure the database engine.
8.  Configure an async session factory.
9.  Create a first SQLAlchemy model.
10. Configure Alembic and create the first migration.
11. Add a readiness endpoint that checks dependencies.
12. Add tests for health and database connectivity.

### Important distinction: liveness vs readiness

-   Liveness answers: is the application process alive?
-   Readiness answers: can the application currently serve its intended
    work?

A process may be alive while PostgreSQL or Redis is unavailable.

### Understand the session pattern

The documented FastAPI dependency uses an async context manager:

``` python
async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session
```

The session is closed when the dependency scope exits.

The engine configuration uses:

-   `pool_pre_ping=True`
-   `pool_size=10`
-   `max_overflow=20`
-   `expire_on_commit=False` in the session factory

Understand what each setting means before changing it.

### M1 completion criteria

-   API starts.
-   PostgreSQL starts.
-   Redis starts.
-   Migrations apply.
-   Liveness and readiness work.
-   Tests can connect to the required services.

## 28. M2 --- Implement tenants and API keys

### Goal

Give each tenant an identity and a credential that can authenticate
requests.

### Concepts

-   Relational data modelling.
-   Foreign keys.
-   Random secrets.
-   Hashing.
-   Authentication.
-   Credential rotation.
-   Revocation.
-   Authorization.

### API-key design

The documented key format has:

-   A public 16-character hexadecimal lookup prefix.
-   A 256-bit random secret.

The prefix helps locate a candidate record.

The secret proves possession of the credential.

The database stores a SHA-256 hash, not the plaintext key.

Why SHA-256 here?

API keys are generated with high entropy. They are not human-chosen
passwords. A fast cryptographic hash is suitable for verifying these
randomly generated secrets. Do not copy this approach for storing human
passwords.

### Key lifecycle

``` mermaid
flowchart TD
    Create[Issue API key] --> Generate[Generate random secret]
    Generate --> Prefix[Create public lookup prefix]
    Prefix --> Hash[Hash secret]
    Hash --> Store[Store prefix and hash]
    Store --> Return[Return plaintext once]
    Return --> Use[Client uses bearer key]
    Use --> Verify[Locate and verify hash]
    Verify --> Revoke[Revoke or rotate when needed]
```

### Required behaviours

-   Create a tenant.
-   Issue a key.
-   List key metadata without exposing plaintext.
-   Authenticate a valid key.
-   Reject invalid, expired, or revoked keys.
-   Revoke a key.
-   Rotate a key and revoke the old key.

### Security rules

-   Never store plaintext API keys.
-   Never log bearer tokens.
-   Never put real credentials in Git.
-   Compare secret hashes using constant-time comparison.
-   Return the plaintext key only once.

### M2 completion criteria

A tenant can be created, issued a key, authenticated, revoked, and
rotated through the API.

## 29. M3 --- Implement the rate-limiting foundation

### Goal

Implement the algorithms independently of HTTP and Redis.

### Concepts

-   Interfaces and contracts.
-   Algorithms.
-   Monotonic time.
-   Thread safety.
-   Deterministic testing.
-   Policy resolution.

### Recommended order

1.  Define a common decision structure.
2.  Define the limiter interface.
3.  Implement Token Bucket.
4.  Implement Fixed Window.
5.  Implement Sliding Window Log.
6.  Add deterministic clock injection.
7.  Add tests for boundaries and retry calculations.
8.  Implement policy CRUD.
9.  Implement endpoint-pattern matching.
10. Test policy precedence and ambiguity.

### Why use monotonic time?

Wall-clock time can change due to clock synchronization or manual
adjustment.

For measuring elapsed time inside a process, a monotonic clock is safer
because it is designed not to move backwards.

The documented in-process Token Bucket uses `time.monotonic()` and
supports an injected clock for deterministic tests.

### Policy resolution

Given these policies:

``` text
*
/api/v1/*
/api/v1/users
```

For `/api/v1/users`, the exact path wins.

For `/api/v1/orders`, the prefix wins.

For another unmatched eligible path, the catch-all may apply.

### M3 completion criteria

-   All three algorithms work independently.
-   Edge cases have tests.
-   Policy CRUD works.
-   Exact, prefix, and fallback matching behave correctly.

## 30. M4 --- Move enforcement into Redis

### Goal

Make quota state shared between multiple API processes.

### Concepts

-   Redis data structures.
-   Lua scripting.
-   Atomic operations.
-   TTL and expiration.
-   Middleware.
-   Dependency failures.
-   HTTP response headers.

### Recommended order

1.  Define the Redis key scheme.
2.  Write the Token Bucket Lua script.
3.  Test it against Redis.
4.  Write the Fixed Window Lua script.
5.  Test it against Redis.
6.  Write the Sliding Window Log Lua script.
7.  Test it against Redis.
8.  Implement the Redis rate-limit engine.
9.  Add the FastAPI middleware.
10. Add the authenticated principal to request state.
11. Reuse the principal in endpoint dependencies.
12. Add rate-limit response headers.
13. Implement fail-closed behaviour.
14. Implement optional fail-open behaviour.
15. Add metrics for allowed, denied, and dependency-error outcomes.
16. Test concurrency against a dedicated Redis database.

### Middleware decision flow

``` mermaid
flowchart TD
    Request[Incoming request] --> Eligible{Eligible API route?}
    Eligible -->|No| Continue[Continue request]
    Eligible -->|Yes| Key{Bearer key present?}
    Key -->|No| Continue
    Key -->|Yes| Auth[Authenticate with PostgreSQL]
    Auth --> Valid{Valid tenant?}
    Valid -->|No| Continue
    Valid -->|Yes| Load[Load active policies]
    Load --> Resolve[Resolve matching policy]
    Resolve --> Match{Policy found?}
    Match -->|No| Continue
    Match -->|Yes| Redis[Execute Redis Lua decision]
    Redis --> Available{Redis decision succeeded?}
    Available -->|No| FailMode{Fail-open enabled?}
    FailMode -->|Yes| Continue
    FailMode -->|No| Unavailable[HTTP 503]
    Available -->|Yes| Allowed{Quota allowed?}
    Allowed -->|Yes| Continue
    Allowed -->|No| Denied[HTTP 429]
```

### Why does authentication failure not use fail-open?

Fail-open is intended to handle a failed rate-limit decision when Redis
is unavailable.

It must not become a way to bypass tenant authentication or database
identity checks.

Sentinel's documented behaviour keeps authentication and PostgreSQL
failures closed.

### M4 completion criteria

-   All algorithms execute through Redis.
-   Quota state is shared between API processes.
-   Concurrent requests do not over-admit beyond the tested quota.
-   Middleware returns correct status codes and headers.
-   Redis outage behaviour is tested.
-   Metrics record decisions and failures.

## 31. M5 --- Measure, observe, and operate the service

### Goal

Understand how the system behaves under load and during dependency
failures.

### Concepts

-   Load testing.
-   Throughput.
-   Latency percentiles.
-   CPU and memory.
-   Profiling.
-   Redis memory and TTL.
-   Prometheus.
-   Grafana.
-   Multi-process testing.

### Important metrics

**Throughput**

Requests completed per second.

**Average latency**

Mean time taken to complete a request.

**Median latency**

The 50th percentile. Half of observations are at or below this value.

**p95 latency**

95% of observations are at or below this value.

**p99 latency**

99% of observations are at or below this value.

**Error rate**

The proportion of requests that fail according to the test's definition
of failure.

A test reporting zero failures does not necessarily mean every request
returned HTTP 200. Sentinel's documented Locust task counts HTTP 200 and
HTTP 429 as successful test outcomes.

### Load-test workflow

1.  Create a dedicated load-test tenant.
2.  Issue a dedicated API key.
3.  Create a policy suitable for the load test.
4.  Put the key in `SENTINEL_TEST_API_KEY`.
5.  Run Locust.
6.  Increase user count gradually.
7.  Observe throughput and latency.
8.  Observe container resource use.
9.  Compare runs and identify where latency begins to rise sharply.

Do not run load tests against production credentials or production data.

### Historical local observations

The documented local tests reported:

    Users   Requests    Throughput   Median     p95      p99
  ------- ---------- ------------- -------- ------- --------
        5      2,366   131.9 req/s     8 ms   14 ms    16 ms
       10     14,825   258.3 req/s    10 ms   20 ms    26 ms
       25     19,895   343.6 req/s    42 ms   83 ms   110 ms

These are observations from one local development environment, not
production capacity guarantees.

At 25 users, throughput increased but latency also rose sharply. One
Docker stats snapshot showed the API near one CPU core and PostgreSQL
using a substantial amount of CPU, while Redis CPU use was comparatively
low. This is a clue for further profiling, not proof of the bottleneck.

### Observability

Prometheus scrapes the `/metrics` endpoint.

Grafana visualizes metrics such as:

-   HTTP requests per second.
-   Rate-limit decisions.
-   HTTP p95 and p99 latency.
-   HTTP status classes.
-   Allowed and denied requests.

The included metrics collector is process-local. The documented Grafana
dashboard is intended for a single-worker local deployment.

Redis quota state is shared independently of the metrics collector.

### M5 completion criteria

-   Repeatable load-test workflow.
-   Algorithm benchmarks.
-   Profiling workflow.
-   Redis diagnostics.
-   Prometheus metrics.
-   Grafana dashboard.
-   Failure-mode experiments.
-   Cross-process integration tests.
-   Known operational limitations documented.

------------------------------------------------------------------------

# Part VII --- Understand the codebase

## 32. How to read the code without getting lost

Do not read every file randomly.

Follow the request path.

A useful reading order is:

1.  `app/main.py` --- application creation and lifecycle.
2.  `app/core/config.py` --- configuration and environment settings.
3.  `app/db/session.py` --- SQLAlchemy engine and session factory.
4.  `app/db/dependencies.py` --- request-scoped database session
    dependency.
5.  `app/middleware.py` --- the main rate-limit request flow.
6.  `app/services/api_key_service.py` --- API-key authentication and
    lifecycle logic.
7.  `app/limiter/policy_resolution.py` --- policy selection.
8.  Redis limiter implementation and Lua scripts --- shared quota
    decisions.
9.  `app/api/routes/admin.py` --- tenant, key, and policy management
    endpoints.
10. `app/api/dependencies/authentication.py` --- endpoint-level
    principal dependency.
11. `app/limiter/metrics.py` and `app/api/routes/metrics.py` --- metrics
    collection and exposition.
12. Tests --- the executable specification of expected behaviour.

This list includes paths identified in the project documentation and
inspected code. Explore the repository for the exact names of the Redis
engine, Lua script, model, and test files.

## 33. Understand the middleware first

The middleware is the best entry point for understanding the runtime
request flow.

Its high-level responsibilities are:

-   Determine whether the request should be rate limited.
-   Extract the bearer credential.
-   Authenticate the key.
-   Load active policies.
-   Resolve the matching policy.
-   Call Redis.
-   Handle allowed, denied, and dependency-error outcomes.
-   Attach headers to allowed responses.

The middleware should orchestrate the flow, not contain every algorithm
implementation itself.

## 34. Understand database sessions

The inspected session dependency is:

``` python
async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session
```

This creates a session for the dependency scope and closes it when the
scope exits.

The inspected middleware also creates a session using an async context
manager for authentication and policy reads. Its session scope exits
before the Redis decision is executed.

This is important when diagnosing database connection and transaction
behaviour.

A session context manager handles session closure. It does not mean
every transaction is automatically committed. Unfinished transactions
are rolled back when the session is closed.

## 35. Understand the API-key service

The middleware calls the API-key authentication service.

Read it to understand:

-   How the public prefix is used.
-   How a candidate key record is found.
-   How the presented secret is verified.
-   How tenant status is checked.
-   What happens for invalid, revoked, or expired keys.

Do not assume a key is valid just because its prefix exists.

## 36. Understand policy resolution

Policy resolution is separate from authentication.

The resolver receives a set of active policies and a request path.

It must choose the most specific matching policy.

Test the resolver independently from FastAPI and Redis. This makes bugs
easier to isolate.

## 37. Understand the Redis engine

The Redis engine should translate a policy and tenant identity into the
appropriate Redis operation.

Read it together with the Lua scripts.

For each algorithm, ask:

1.  What Redis keys are used?
2.  What data is stored?
3.  What is the time source?
4.  What happens when quota remains?
5.  What happens when quota is exhausted?
6.  How is retry time calculated?
7.  How is expiry managed?
8.  What happens if Redis raises an error?

Do not treat a Lua script as magic. Trace every key read and write.

------------------------------------------------------------------------

# Part VIII --- How to test the system properly

## 38. The testing pyramid

Use multiple levels of tests.

``` text
            End-to-end tests
         Integration tests
       Unit and algorithm tests
```

### Unit tests

Test isolated logic:

-   Token Bucket refill.
-   Fixed Window boundary.
-   Sliding Window expiration.
-   Policy matching.
-   Key parsing and hashing.

These tests should be fast and deterministic.

### Integration tests

Test components together:

-   SQLAlchemy and PostgreSQL.
-   Redis Lua scripts and real Redis.
-   Middleware and dependency behaviour.
-   Redis TTL.
-   Multiple API processes sharing quota state.

### End-to-end tests

Test complete HTTP workflows:

1.  Create tenant.
2.  Issue API key.
3.  Create policy.
4.  Call protected endpoint.
5.  Exceed quota.
6.  Observe HTTP 429.
7.  Revoke key.
8.  Confirm authentication no longer succeeds.

## 39. Test concurrency, not just sequential requests

A sequential test does not prove atomicity under concurrency.

Suppose the initial quota is 10.

Send 50 concurrent requests.

The expected result for the documented integration scenario is exactly
10 admissions.

Why?

All requests compete for the same shared quota. The Redis script must
serialize the relevant decision and update.

The integration tests documented for Sentinel use 50 concurrent requests
and assert exactly 10 admissions for a 10-request initial quota.

Use a dedicated Redis logical database for these tests.

## 40. Test failure behaviour

Test these separately:

  -----------------------------------------------------------------------
  Dependency condition                Expected behaviour
  ----------------------------------- -----------------------------------
  PostgreSQL unavailable during       Fail closed
  authentication                      

  Redis unavailable, fail-closed mode HTTP 503

  Redis unavailable, fail-open mode   Continue after successful
                                      authentication and policy lookup

  Redis restored                      Normal quota enforcement resumes
  -----------------------------------------------------------------------

Do not stop PostgreSQL and Redis simultaneously when trying to test
Redis-specific fail-open behaviour. Authentication and policy lookup
still require PostgreSQL.

------------------------------------------------------------------------

# Part IX --- Operate Sentinel locally

## 41. Windows PowerShell setup

From the project directory:

``` powershell
Set-Location C:\code\sentinel-m5

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e ".[dev]"

Copy-Item .env.example .env
```

Configure the admin secret in `.env`, then start the stack:

``` powershell
docker compose --profile monitoring up -d --build
docker compose ps
```

Check application health:

``` powershell
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready
```

Run tests:

``` powershell
pytest -v
```

## 42. Useful endpoints

  Purpose                 URL
  ----------------------- ------------------------------------
  Swagger documentation   http://localhost:8000/docs
  Liveness                http://localhost:8000/health/live
  Readiness               http://localhost:8000/health/ready
  Metrics                 http://localhost:8000/metrics
  Prometheus              http://localhost:9090
  Grafana                 http://localhost:3000
  Locust                  http://localhost:8089

## 43. Environment variables

The application uses the `SENTINEL_` prefix for settings.

Important variables include:

  Variable                          Purpose
  --------------------------------- ---------------------------
  `SENTINEL_APP_NAME`               Application name
  `SENTINEL_ENVIRONMENT`            Environment name
  `SENTINEL_DATABASE_URL`           PostgreSQL connection URL
  `SENTINEL_REDIS_URL`              Redis connection URL
  `SENTINEL_LOG_LEVEL`              Logging level
  `SENTINEL_ADMIN_API_KEY`          Admin bootstrap secret
  `SENTINEL_RATE_LIMIT_FAIL_OPEN`   Redis failure behaviour
  `SENTINEL_UVICORN_WORKERS`        Uvicorn worker count

Keep `.env` out of Git.

The Compose project `.env` file is used for variable interpolation. A
service's `env_file` passes variables into the container. Explicit
`environment` values override matching `env_file` values.

## 44. Common troubleshooting

### API connection refused

The API may still be starting.

``` powershell
docker compose ps
docker compose logs --tail 40 api
Invoke-RestMethod http://localhost:8000/health/ready
```

### PostgreSQL connection failure

Check the PostgreSQL container:

``` powershell
docker compose ps postgres
docker compose logs --tail 40 postgres
```

Remember: inside the API container, use the Compose service hostname,
not `localhost`.

### Redis connection failure

``` powershell
docker compose ps redis
docker compose logs --tail 40 redis
```

### HTTP 401

Check:

-   Whether the current API key variable is populated.
-   Whether the key was copied correctly.
-   Whether the key has expired.
-   Whether the key was revoked.
-   Whether the tenant is active.

### HTTP 429

Redis made a quota decision and the policy limit was exceeded.

### HTTP 503

A required dependency failed under fail-closed behaviour. Inspect API
logs and dependency health.

### Lost API key after closing PowerShell

The plaintext key is returned only once. The database stores the hash,
not a retrievable plaintext value.

If the key is lost, issue a replacement or rotate it. Do not expect to
recover the original plaintext.

------------------------------------------------------------------------

# Part X --- Performance reasoning and limitations

## 45. Why the first bottleneck may not be Redis

A request can involve:

1.  PostgreSQL API-key lookup.
2.  PostgreSQL tenant validation.
3.  PostgreSQL policy lookup.
4.  Redis network round trip.
5.  Redis Lua execution.
6.  Endpoint execution.
7.  Response serialization.

A slow request does not automatically mean Redis is slow.

Measure each dependency and profile the application before optimizing.

The documented local 25-user load test showed the API container near one
CPU core and PostgreSQL using a substantial amount of CPU in one
resource snapshot. Redis CPU use was comparatively low. This suggests
places to investigate, but does not establish a definitive bottleneck.

## 46. Why caching is deferred

Sentinel currently loads authentication and policy data from PostgreSQL
on every authenticated request.

Caching could reduce database work, but introduces correctness
questions:

-   How quickly does a revoked key stop working?
-   How quickly does a policy update take effect?
-   How do multiple API workers invalidate cached data?
-   What happens if the cache is unavailable?
-   How do we prevent stale authorization?

A cache is not just a performance feature. It changes consistency and
revocation semantics.

## 47. Multi-worker metrics limitation

The included metrics collector is process-local.

With four Uvicorn workers:

``` text
Worker 1 -> its own counters
Worker 2 -> its own counters
Worker 3 -> its own counters
Worker 4 -> its own counters
```

A scrape served by one worker does not necessarily include the other
workers' metrics.

This does not mean quota state is process-local. Redis quota state is
shared.

Production metrics need a multiprocess collection or external
aggregation strategy.

## 48. Redis failure and durability

Lua atomicity means the script's operations are not interleaved with
other Redis commands on the executing primary.

It does not guarantee:

-   Consensus across Redis nodes.
-   No data loss during failover.
-   Persistent quota state after every crash.
-   Correct behaviour under every eviction or memory policy.

The local Redis Compose service uses a 256 MB memory ceiling and
`noeviction`. When full, writes fail rather than silently evicting live
quota keys.

Production Redis configuration requires deployment-specific memory
sizing, persistence, replication, and failover decisions.

## 49. Known project limitations

-   Authentication and policy reads hit PostgreSQL on every
    authenticated request.
-   The admin bootstrap secret is not a complete RBAC system.
-   Key rotation immediately revokes the old key; there is no grace
    period.
-   Middleware request cost is fixed at one unit.
-   Sliding Window Log stores individual events and has O(n) retry
    calculation.
-   In-process educational limiter state and lock objects do not have
    idle-key eviction.
-   Metrics are process-local.
-   Redis failover or data loss can reset recent quota state.
-   The manual four-worker quota experiment was inconclusive because its
    sequential request batch crossed a fixed-window boundary.
-   The fail-closed HTTP 503 behaviour was manually verified, but the
    corresponding fail-closed metric was not independently verified in
    the recorded experiment.
-   The historical test result of 95 passed, 1 warning, and 0 skipped
    must not be presented as a fresh run.

------------------------------------------------------------------------

# Part XI --- What Sentinel is and is not

## 50. Is Sentinel a complete reverse proxy?

No. The documented implementation is a FastAPI application with
middleware that authenticates requests and enforces quotas on its own
API routes.

A full reverse proxy would also need to forward requests to upstream
services, manage upstream routing, handle response streaming, timeouts,
connection pooling, and additional proxy concerns.

Do not describe the current project as a fully featured reverse proxy.

## 51. Can another backend use Sentinel?

The current management APIs can create tenants, keys, and policies. The
current protected endpoint demonstrates enforcement inside the Sentinel
application.

For an external company's backend to use Sentinel as a centralized
rate-limit service, the product would need a deliberate integration
interface, such as:

-   An internal decision endpoint.
-   A client SDK.
-   Authentication and authorization for service-to-service callers.
-   A clear tenant identity contract.
-   A timeout and failure policy.
-   A deployment and network-security model.

That integration interface is a product extension, not something to
assume is already complete.

## 52. What would be needed to turn it into a hosted SaaS product?

A hosted product would need additional capabilities:

-   Organization/account model.
-   Organization membership and roles.
-   User login and session management.
-   Organization-scoped authorization.
-   A web dashboard.
-   Secure organization onboarding.
-   Billing and subscription management, if monetized.
-   Audit logs.
-   Operational alerting.
-   Stronger production deployment and secrets management.

The current tenant model should not be confused with a full organization
model.

------------------------------------------------------------------------

# Part XII --- Learn to explain Sentinel in an interview

## 53. Explain the project in 30 seconds

> Sentinel is a multi-tenant rate-limiting service built with FastAPI,
> PostgreSQL, and Redis. PostgreSQL stores tenants, API-key metadata,
> and rate-limit policies. FastAPI middleware authenticates incoming
> requests and resolves the appropriate tenant policy. Redis Lua scripts
> execute Token Bucket, Fixed Window, and Sliding Window Log decisions
> atomically, allowing quota state to be shared across API workers. The
> project also includes failure handling, Prometheus metrics, Grafana
> dashboards, and Locust-based performance testing.

## 54. Explain the architecture in two minutes

Start with the problem: customers need independent usage limits.

Then explain:

1.  PostgreSQL stores durable identity and policy configuration.
2.  API keys identify tenants.
3.  Middleware authenticates the request and resolves the matching
    policy.
4.  Redis holds shared quota state.
5.  Lua makes the quota decision atomic.
6.  HTTP 429 means the quota was exceeded.
7.  HTTP 503 means the limiter dependency was unavailable in fail-closed
    mode.
8.  Prometheus and Grafana provide observability.
9.  Locust measures behaviour under load.

## 55. Questions you should be able to answer

### Architecture

-   Why use PostgreSQL and Redis instead of only PostgreSQL?
-   Why is Redis state shared between workers?
-   What happens if an API worker restarts?
-   What happens if Redis restarts?
-   Why are tenant IDs part of Redis keys?

### Algorithms

-   How does Token Bucket work?
-   Why can Fixed Window allow boundary bursts?
-   Why is Sliding Window Log more memory-intensive?
-   What is the difference between average rate and burst capacity?
-   How is retry time calculated?

### Concurrency

-   What is a race condition?
-   Why can separate Redis commands over-admit?
-   What does atomic Lua execution guarantee?
-   What does it not guarantee across Redis failover?

### Security

-   Why store API-key hashes rather than plaintext?
-   Why have a public lookup prefix?
-   Why use constant-time comparison?
-   Why must authentication fail closed?
-   How do key revocation and rotation work?

### Operations

-   What is the difference between liveness and readiness?
-   What does p95 latency mean?
-   Why is zero Locust failures not the same as zero HTTP 429 responses?
-   Why are metrics process-local?
-   How would you diagnose a database bottleneck?

If you cannot answer a question, return to the relevant implementation
and tests. Do not memorize an answer without understanding the code.

------------------------------------------------------------------------

# Part XIII --- A practical study plan

## 56. Suggested 14-session learning sequence

Each session should end with a working explanation or a small test, not
merely reading.

  ------------------------------------------------------------------------
                       Session Study topic           Deliverable
  ---------------------------- --------------------- ---------------------
                             1 HTTP, REST, FastAPI   Explain a
                                                     request/response
                                                     cycle

                             2 Async Python          Explain `async`,
                                                     `await`, and I/O
                                                     waiting

                             3 PostgreSQL and SQL    Draw the
                                                     tenant/key/policy
                                                     relationships

                             4 SQLAlchemy async      Explain engine, pool,
                                                     session, and
                                                     transaction

                             5 Redis                 Explain keys,
                                                     counters, TTL, and
                                                     shared state

                             6 Token Bucket          Implement and test it
                                                     independently

                             7 Fixed Window          Implement and test
                                                     its boundary
                                                     behaviour

                             8 Sliding Window Log    Implement and test
                                                     timestamp expiry

                             9 Middleware and        Trace a protected
                               authentication        request

                            10 Policy resolution     Test exact, prefix,
                                                     and fallback
                                                     precedence

                            11 Redis Lua             Explain and test
                                                     atomic quota
                                                     decisions

                            12 Failure handling      Reproduce 429, 503,
                                                     fail-open, and
                                                     recovery

                            13 Observability and     Read metrics and
                               Locust                interpret latency
                                                     percentiles

                            14 Full architecture     Explain Sentinel
                               review                without looking at
                                                     notes
  ------------------------------------------------------------------------

This is a suggested learning schedule, not a promise that every topic
can be mastered in one session.

## 57. The most effective way to study the code

For every important function, answer these questions:

1.  What problem does this function solve?
2.  Who calls it?
3.  What inputs does it receive?
4.  What does it return?
5.  Which external systems does it access?
6.  What can fail?
7.  How is failure handled?
8.  Which test proves its behaviour?

Then trace one request from the HTTP entry point all the way to Redis
and back.

Do not begin by memorizing every file. Understand the data flow first.

------------------------------------------------------------------------

# Final checklist --- Can you genuinely reproduce Sentinel?

You should be able to check each item without relying on this guide for
the answer.

## Fundamentals

-   [ ] Explain HTTP requests, responses, headers, and status codes.
-   [ ] Explain Python async and await.
-   [ ] Explain relational tables, foreign keys, and transactions.
-   [ ] Explain Redis keys and TTL.
-   [ ] Explain Docker Compose networking.

## Application

-   [ ] Start FastAPI.
-   [ ] Connect PostgreSQL and Redis.
-   [ ] Explain the SQLAlchemy async session lifecycle.
-   [ ] Create and migrate database models.
-   [ ] Create a tenant.
-   [ ] Issue, authenticate, revoke, and rotate API keys.
-   [ ] Create and resolve rate-limit policies.

## Algorithms

-   [ ] Implement Token Bucket independently.
-   [ ] Implement Fixed Window independently.
-   [ ] Implement Sliding Window Log independently.
-   [ ] Explain the trade-offs among the three.

## Distributed enforcement

-   [ ] Explain the race condition in a non-atomic counter.
-   [ ] Explain how Redis Lua addresses it.
-   [ ] Explain Redis server time.
-   [ ] Explain tenant/policy/version key scoping.
-   [ ] Test concurrent requests against a shared quota.

## Operations

-   [ ] Reproduce fail-closed behaviour.
-   [ ] Reproduce fail-open behaviour.
-   [ ] Explain 429 versus 503.
-   [ ] Read Prometheus metrics.
-   [ ] Explain the single-worker dashboard limitation.
-   [ ] Run Locust and interpret p95/p99.
-   [ ] Explain the known limitations honestly.

## Final understanding

-   [ ] Trace a request from HTTP entry to database authentication,
    policy resolution, Redis decision, and response.
-   [ ] Explain why each technology is used.
-   [ ] Identify what is implemented and what remains a future
    extension.
-   [ ] Rebuild the project in milestones without blindly copying
    commands.

If you can do these things, you are no longer just someone who can run
Sentinel. You understand the engineering decisions behind it.

------------------------------------------------------------------------

# Closing thought

The objective of this project is not to accumulate technologies or make
a README look impressive.

The objective is to understand how a backend system behaves when
multiple tenants, concurrent requests, shared state, failures, and
operational constraints interact.

Build the smallest correct version first. Test it. Observe it. Then
introduce the next layer of complexity.

That is how you learn backend engineering.
