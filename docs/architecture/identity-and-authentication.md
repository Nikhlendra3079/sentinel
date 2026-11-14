# Identity and authentication model

## Identity vocabulary

- **Tenant:** the customer/organization that owns resources and rate-limit policies.
- **API key:** a machine credential owned by exactly one tenant.
- **Principal:** the authenticated tenant ID and API-key ID attached to the current request.
- **Administrator:** a separate management identity represented in this milestone by a bootstrap secret.

## API key format

`sk_live_<16-hex-character-public-prefix>_<256-bit-random-secret>`

The prefix is an indexed lookup hint, not a credential. The complete key is hashed with SHA-256 and only the digest is persisted. This is appropriate because the secret is generated with 256 bits of cryptographic randomness. Human passwords require a slow password-hashing algorithm such as Argon2id instead.

The key is returned once at issuance/rotation. Listing keys returns metadata only.

## Authentication flow

1. Parse the HTTP Bearer credential.
2. Validate its syntax and extract the public prefix.
3. Fetch the candidate API-key record and tenant using the indexed prefix.
4. Hash the presented key and compare it to the stored digest with `secrets.compare_digest`.
5. Reject revoked, expired, or non-active tenant credentials.
6. Return a small immutable `TenantPrincipal` to the endpoint.

The tenant ID supplied by a client is never trusted as proof of identity.

## Administrative routes

Management routes use `X-Admin-Token`, compared against `SENTINEL_ADMIN_API_KEY` using `secrets.compare_digest`. This is deliberately a bootstrap mechanism for the learning project. It is not fine-grained RBAC, has no per-admin audit identity, and must not be treated as a production admin system. A later milestone can replace it with persisted admin users, roles, scoped permissions, and audit events.

## Transactions

Key rotation is one database transaction:

1. Lock the old key row using `SELECT ... FOR UPDATE`.
2. Mark the old key revoked.
3. Insert the replacement key hash and prefix.
4. Commit both changes together.

If insertion fails, the transaction rolls back and the old key remains active. Concurrent rotations serialize on the old key row; only one should succeed.

## Deliberate limitations

- Each authenticated request currently queries PostgreSQL. A later milestone will introduce a cache only after defining revocation and policy-update consistency.
- Revocation takes effect on the next authentication query; no cache invalidation problem exists yet because there is no auth cache.
- There is no grace period during key rotation.
- Administrative credentials are shared rather than individual.
- API keys are bearer tokens: anyone possessing one can use it. TLS is required outside local development.
