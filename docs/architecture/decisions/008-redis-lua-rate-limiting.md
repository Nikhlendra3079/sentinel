# ADR 008 — Redis Lua for distributed rate-limit decisions

## Status

Accepted for M4.

## Context

M3's per-key locks protect only one Python process. Multiple Uvicorn workers or machines would maintain independent quotas. Splitting a decision into ordinary Redis read and write commands introduces a race between concurrent workers.

## Decision

Use Redis Lua scripts for each algorithm. Each script performs the full read/expire/refill/check/update transition atomically. Use Redis server `TIME` as the common clock. Scope keys by tenant, policy, and policy version; use a shared Redis Cluster hash tag for multi-key scripts. Add TTLs to all state.

## Consequences

- Workers share a single decision point for a policy key.
- Policy version changes start fresh state; previous state expires naturally.
- Sliding Window Log uses a sorted set plus event-cost hash and running usage value.
- Lua execution blocks Redis while the script runs; sliding-window work is proportional to expired/active events.
- Redis failover, eviction, or data loss can still reset quotas. Atomic execution is not a durability guarantee.
