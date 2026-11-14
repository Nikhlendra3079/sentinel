# Sliding Window Log

## Semantics

The limiter enforces a maximum request-cost budget over the rolling interval
`(now - window_seconds, now]`. An event exactly at the cutoff is expired.

For each key, it stores an ordered deque of `(monotonic_timestamp, cost)`
events and a running sum. Every consume operation prunes expired events,
checks the weighted total, and appends the new event only when allowed.

## Complexity

Appending and reading the running usage total are O(1). Pruning and the
weighted retry-after scan are O(k), where k is the number of expired or
scanned events. Each admitted event is appended once and pruned once, so
pruning is amortized O(1) per event over its lifetime.

## Trade-offs

The log gives precise rolling-window enforcement, but memory usage grows
with the number of admitted requests during the active window. It is
process-local and protected by per-key locks; it is not distributed across
multiple application workers. A production distributed version can use a
Redis sorted set and an atomic Lua script.

`reset_after_seconds` means the time until all currently active usage has
expired. `retry_after_seconds` means the earliest time enough usage expires
to admit the requested cost.
