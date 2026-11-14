# ADR-004: High-entropy API keys are stored as SHA-256 hashes

- Status: Accepted
- Decision: Generate 256-bit random API keys, include a non-secret public lookup prefix, and persist only the SHA-256 digest of the complete key.
- Context: API keys are machine-generated high-entropy bearer credentials. A fast cryptographic hash is appropriate for this use case; password hashing is designed for low-entropy human passwords and is not required for random 256-bit tokens.
- Consequences: The original key is shown only once. Lost keys must be rotated. The prefix narrows the database lookup but is not an authentication factor. Hash equality is checked with `secrets.compare_digest`.
- Security notes: Never log the Authorization header or plaintext key. Use TLS in deployed environments. Keep administrative credentials separate from tenant API keys.
