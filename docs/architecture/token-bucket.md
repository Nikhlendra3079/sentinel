# Token bucket algorithm

## State

For each bucket key, store:

- `tokens`: current fractional token balance
- `updated_at`: monotonic timestamp at which the balance was last calculated

Configuration:

- `capacity`: maximum token balance
- `refill_rate`: tokens added per second

## Transition

At time `now`:

1. Clamp time so it never moves behind the stored timestamp.
2. Calculate elapsed seconds.
3. Refill by `elapsed * refill_rate`, capped at capacity.
4. If request cost fits, deduct it and allow.
5. Otherwise preserve the refilled balance and reject.
6. Return remaining capacity, retry delay, and time to a full bucket.

The refill calculation is persisted on rejected attempts too. This prevents the same elapsed interval from being counted repeatedly.

## Time source

Use a monotonic clock for in-process elapsed-time calculations. Wall-clock time can jump because of NTP adjustments or manual clock changes. Tests inject a fake monotonic clock so no test needs to sleep.

## Concurrency

The in-process implementation uses a per-key thread lock. The lock registry itself has a guard so two threads cannot create different locks for the same key concurrently.

This only coordinates threads inside one Python process. It does not coordinate multiple worker processes or machines. The distributed implementation will use a Redis Lua script to perform read, refill, decision, deduction and state update atomically.

## Complexity and limitations

- Expected lookup: O(1) average for the Python dictionary.
- Per-key consume: O(1) work, excluding lock contention.
- Memory: O(number of distinct keys ever seen); this prototype has no idle-key eviction.
- State is lost when the process restarts.
- Multiple Uvicorn workers each have independent buckets.

These limitations are intentional in this milestone and must not be mistaken for distributed correctness.
