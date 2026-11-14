# Fixed-window counter

## Model

A fixed-window limiter assigns each request to an epoch-aligned interval of
length `W` seconds. For Unix timestamp `t`:

```text
window_id = floor(t / W)
window_end = (window_id + 1) * W
reset_after = window_end - t
```

Each key has a counter `C` for its current window. A request of cost `q` is
allowed exactly when `C + q <= L`, where `L` is the configured limit. Allowed
requests increment `C`; denied requests leave it unchanged.

## Decision semantics

- `remaining`: `max(0, L - C)` after an allowed request, or before the denied
  request when denied.
- `retry_after_seconds`: zero for an allowed request; seconds until the next
  window boundary for a denied request.
- `reset_after_seconds`: seconds until the current window ends.

A request whose cost exceeds `L` can never be admitted, even in a fresh window,
so its `retry_after_seconds` is `None`. A request that fits in an empty window
but not in the remaining quota is retryable at the next window boundary.

## Concurrency and clock

A per-key thread lock makes the in-process counter transition atomic between
threads. Windows are aligned to Unix epoch boundaries, so the default clock is
`time.time`, not `time.monotonic`. The implementation clamps a backwards clock
to the last timestamp observed for that key to avoid rolling a key into an
older window and accidentally granting quota again.

Wall-clock adjustments and independent clocks across processes remain reasons
not to use this implementation for distributed enforcement. A Redis-backed
version should calculate time and update the counter atomically using a shared
server-side clock (for example, Redis `TIME` inside a Lua script).

## Trade-off: boundary burst

Fixed windows can admit nearly `2L` requests in a very short interval around a
boundary: up to `L` just before the boundary and another `L` immediately after
it. This is the algorithm's defining weakness, not an implementation bug.

## State lifecycle

Only the most recently observed window is stored per key, so old window
counters are replaced lazily on the next request. The key state and its lock
are still retained indefinitely; key eviction is deferred.
