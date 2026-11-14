import hashlib
import secrets
from dataclasses import dataclass


API_KEY_PREFIX = "sk_live_"
PUBLIC_PREFIX_BYTES = 8
SECRET_BYTES = 32


@dataclass(frozen=True, slots=True)
class GeneratedApiKey:
    full_key: str
    public_prefix: str
    key_hash: str


def generate_api_key() -> GeneratedApiKey:
    """Generate a high-entropy API key and the values safe to persist."""
    public_prefix = secrets.token_hex(PUBLIC_PREFIX_BYTES)
    secret = secrets.token_urlsafe(SECRET_BYTES)
    full_key = f"{API_KEY_PREFIX}{public_prefix}_{secret}"
    return GeneratedApiKey(
        full_key=full_key,
        public_prefix=public_prefix,
        key_hash=hash_api_key(full_key),
    )


def hash_api_key(api_key: str) -> str:
    """Hash a high-entropy API key. This is not a password-hashing function."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def extract_public_prefix(api_key: str) -> str | None:
    """Return the lookup prefix only for keys matching our expected format."""
    parts = api_key.split("_", maxsplit=3)
    if len(parts) != 4:
        return None
    scheme, environment, public_prefix, secret = parts
    if scheme != "sk" or environment != "live":
        return None
    if len(public_prefix) != PUBLIC_PREFIX_BYTES * 2 or not secret:
        return None
    try:
        bytes.fromhex(public_prefix)
    except ValueError:
        return None
    return public_prefix


def verify_api_key(api_key: str, expected_hash: str) -> bool:
    """Constant-time comparison of the calculated and stored SHA-256 digests."""
    actual_hash = hash_api_key(api_key)
    return secrets.compare_digest(actual_hash, expected_hash)
