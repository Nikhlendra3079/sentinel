# ADR-001: Use a modular monolith

- Status: Accepted
- Decision: Deploy one FastAPI application with explicit internal module boundaries.
- Context: The project needs multiple independently testable responsibilities, but does not need independently deployed services yet.
- Consequences: Simpler local development and deployment. Horizontal scaling is achieved by running multiple identical API instances. Module boundaries must be maintained to avoid a monolith becoming tightly coupled.
