# Redis data model and key design

## Shared invariants

- Redis is the authority for rate-limit time. Lua scripts call `TIME`; workers do not pass wall-clock timestamps into the decision.
- Keys are scoped by tenant, policy, and policy version. A policy update increments the database version and therefore selects a fresh state namespace.
- Key names contain a Redis Cluster hash tag: `{tenant_id:policy_id:vN}`. Every key touched by one script has the same tag and therefore maps to one cluster slot.
- No API key, plaintext credential, request body, or raw path is stored in rate-limit state.
- State keys have TTLs. Old policy versions and inactive state expire without a background cleanup job.

## Key shapes

| Algorithm | Redis key | Type | Stored data |
|---|---|---|---|
| Token Bucket | `sentinel:rl:{tenant:policy:vN}:tb` | Hash | `tokens`, `updated_at_ms` |
| Fixed Window | `sentinel:rl:{tenant:policy:vN}:fw` | Hash | `window_id`, `count` |
| Sliding Window Log | `sentinel:rl:{tenant:policy:vN}:sw:events` | Sorted Set | event ID scored by admission timestamp in milliseconds |
| Sliding Window Log | `sentinel:rl:{tenant:policy:vN}:sw:costs` | Hash | event ID to request cost |
| Sliding Window Log | `sentinel:rl:{tenant:policy:vN}:sw:used` | String | total active request cost |
| Sliding Window Log | `sentinel:rl:{tenant:policy:vN}:sw:clock` | String | last observed Redis timestamp (clock rollback guard) |

The braces are Redis Cluster hash tags. The three sliding-window keys are passed together to one Lua script and must share a slot.

## Expiration

- Token Bucket expires after twice the time needed to refill an empty bucket. If the key expires, the bucket would already have become full, so recreating it full preserves the algorithm's idle-state semantics.
- Fixed Window expires shortly after the current window ends.
- Sliding Window keys expire after twice the rolling window. Every request also prunes events outside `(now - window, now]`.
- Redis eviction of live rate-limit keys can grant fresh quota. Production deployments should isolate this state from evictable cache data and use a deliberate memory/eviction policy. `noeviction` plus a configured memory ceiling and capacity planning is the safer correctness-first baseline; an OOM write failure then follows the configured fail-open/fail-closed policy.

## Policy changes

The version is part of the key tag. A policy update intentionally starts a new quota state. Old keys are not synchronously deleted because deleting them is not required for correctness and may race with in-flight requests; TTL handles cleanup.
