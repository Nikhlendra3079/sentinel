# ADR-006: Keep rate-limit algorithms independent of HTTP and storage

- Status: Accepted
- Decision: Define a small `RateLimiterAlgorithm` protocol and a `RateLimitDecision` value object. The first implementation is an in-process token bucket.
- Context: The algorithm must be testable without FastAPI, PostgreSQL or Redis. A later Redis implementation should preserve the same observable decision contract.
- Consequences: The in-process implementation is process-local and is not globally correct across multiple workers or machines. Redis-backed atomic state transitions are required before claiming distributed enforcement.
