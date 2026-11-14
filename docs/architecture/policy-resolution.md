# Policy management and resolution

## Policy patterns

A policy belongs to exactly one tenant and targets one endpoint pattern:

- `*`: tenant-wide fallback.
- `/v1/*`: segment-aware prefix match (matches `/v1` and descendants, not `/v10`).
- `/v1/users`: exact path match.

Only one active policy per tenant and exact pattern is allowed. PostgreSQL enforces this with a partial unique index. Inactive policies may retain the same pattern for history/re-enablement, but only one can be active at a time.

## Precedence

For an incoming path, the resolver considers active matching policies and chooses:

1. Exact path match.
2. Longest matching prefix.
3. Catch-all `*`.

No match means no policy applies. Equal-specificity duplicates are treated as a configuration error rather than selecting one nondeterministically.

## Policy versions

Every PATCH increments `version`. The in-process engine caches algorithm instances by `(policy_id, version)`. A changed version receives a fresh limiter instance and therefore a fresh in-process quota. This is an explicit M3 simplification; a distributed implementation must define whether configuration changes preserve, migrate, or reset existing quota state.

## Algorithm configuration

- Token Bucket: refill rate = `limit_count / window_seconds`; capacity = `burst_capacity` when set, otherwise `limit_count`.
- Fixed Window: limit = `limit_count`; duration = `window_seconds`.
- Sliding Window Log: limit = `limit_count`; rolling duration = `window_seconds`.

`burst_capacity` currently affects Token Bucket only.

## Scope and limitations

The policy CRUD endpoints are administrative APIs. The in-process engine is independently callable and is not yet wired as middleware around every protected endpoint. Its counters are local to one process, disappear on restart, and cannot enforce a shared quota across workers or hosts. Redis atomic execution and request-path integration are subsequent work.
