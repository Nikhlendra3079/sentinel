# ADR-005: Bootstrap administration with a separately configured secret

- Status: Accepted for the learning project
- Decision: Protect initial management endpoints with an administrator secret supplied through `SENTINEL_ADMIN_API_KEY` and the `X-Admin-Token` header.
- Context: Tenant and API-key management must not be public, and a full administrator identity system is outside the current milestone.
- Consequences: The secret must be strong, kept outside source control, rotated operationally, and sent only over TLS outside local development. This is a bootstrap control, not a complete multi-user RBAC system. A future milestone can replace it with persisted admin identities and role-based authorization.
