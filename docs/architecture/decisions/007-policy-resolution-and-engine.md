# Decision 007 — Policy resolution and in-process algorithm engine

## Decision

Resolve policies in deterministic order: exact endpoint path, longest matching segment-aware prefix, then tenant catch-all. Enforce one active policy per tenant and endpoint pattern in PostgreSQL. Cache algorithm instances by policy ID and version.

## Rationale

Specific endpoint overrides should win over broader defaults. Deterministic resolution avoids relying on database row order. Policy-versioned instances make configuration changes explicit and prevent an old algorithm configuration from continuing to execute under a new version.

## Consequences

- Policy updates reset the in-process quota for that policy.
- A policy with no match means no policy is applied.
- Duplicate active patterns are rejected by the database.
- The engine is thread-safe for algorithm instance creation, and each limiter protects its own per-key state.
- State remains process-local; multiple workers and hosts still require a shared atomic backend.
