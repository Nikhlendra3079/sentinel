# ADR-003: Use asynchronous I/O

- Status: Accepted
- Decision: Use FastAPI async endpoints, SQLAlchemy AsyncSession and redis.asyncio.
- Context: Request processing waits on network services.
- Consequences: Avoid blocking I/O inside async request paths. CPU-heavy work may require a process pool or separate worker, but rate-limit decisions should remain small and I/O-oriented.
