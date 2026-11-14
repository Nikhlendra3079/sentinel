# ADR-002: PostgreSQL for durable configuration, Redis for live limiter state

- Status: Accepted
- Decision: PostgreSQL is authoritative for tenants, API keys and policies. Redis is authoritative for mutable rate-limit algorithm state.
- Context: Configuration needs relational constraints and durable storage. Request-time state needs fast shared access and atomic operations.
- Consequences: The system must define how policy changes invalidate or migrate Redis state. Redis persistence is not a substitute for PostgreSQL configuration durability.
