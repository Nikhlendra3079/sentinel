# Atomic distributed rate limiting with Redis Lua

## Why Lua instead of multiple Python Redis commands?

A naïve implementation might `GET` a counter, compare it in Python, then `INCR` it. Two workers can interleave between those operations and both approve the last available unit. A transaction pipeline does not automatically make a read/compute/write decision safe unless the whole operation uses an appropriate optimistic-locking protocol and retries.

Each Sentinel script performs the complete state transition—read, expire/refill, check, mutate, and return—inside one Redis server-side execution. Redis executes a Lua script atomically relative to other commands. Concurrent workers therefore observe a serial order of decisions for a given key set.

## Clock authority

Scripts call Redis `TIME` and convert it to milliseconds. This avoids different application worker clocks granting inconsistent windows or refills. The token bucket stores its last server timestamp; fixed window derives the epoch-aligned window ID; sliding window scores each admission with server time.

## Script complexity

- Token Bucket: O(1) hash operations.
- Fixed Window: O(1) hash operations.
- Sliding Window Log: O(e) for pruning `e` expired events and potentially O(n) to calculate weighted retry-after across active events. The exact log is memory-intensive at high request rates and scripts block Redis while running. Bound policy limits/windows and monitor script latency; consider a sliding-window counter approximation for very high-volume workloads.

## Redis Cluster

The current application bootstrap uses the standard standalone `Redis` client. The key scheme and scripts are cluster-slot-safe, but switching the connection layer to `RedisCluster` and testing cluster redirects/failover is a separate deployment step.

A Lua script that accesses multiple keys must access keys in the same cluster slot. All keys for one sliding-window policy use the same `{tenant:policy:vN}` hash tag. Scripts receive every key through `KEYS`, not by constructing undeclared cross-slot names.

## Consistency boundary

Atomicity applies to one Redis primary's execution of a script. It is not a distributed consensus protocol. Redis failover, asynchronous replication, data loss, eviction, or restore can lose recent quota state. If the product requires strict quota preservation across failover, the storage and replication durability guarantees must be designed accordingly.
