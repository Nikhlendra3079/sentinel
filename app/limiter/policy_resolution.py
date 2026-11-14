from collections.abc import Iterable

from app.models.rate_limit_policy import RateLimitPolicy


def policy_matches(endpoint_pattern: str, path: str) -> bool:
    """Match exact paths, segment-aware prefix patterns ('/v1/*'), or catch-all '*'."""
    if endpoint_pattern == "*":
        return True
    if endpoint_pattern.endswith("/*"):
        prefix = endpoint_pattern[:-2].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return endpoint_pattern == path


def resolve_policy(policies: Iterable[RateLimitPolicy], path: str) -> RateLimitPolicy | None:
    """Choose exact > longest prefix > catch-all among active tenant policies.

    A tie at the same specificity is a configuration error, not an arbitrary
    choice. The database/API layer should prevent duplicate active patterns.
    """
    candidates: list[tuple[tuple[int, int], RateLimitPolicy]] = []
    for policy in policies:
        if not policy.is_active or not policy_matches(policy.endpoint_pattern, path):
            continue
        pattern = policy.endpoint_pattern
        if pattern == "*":
            rank = (0, 0)
        elif pattern.endswith("/*"):
            rank = (1, len(pattern) - 2)
        else:
            rank = (2, len(pattern))
        candidates.append((rank, policy))

    if not candidates:
        return None
    best_rank = max(rank for rank, _ in candidates)
    best = [policy for rank, policy in candidates if rank == best_rank]
    if len(best) > 1:
        raise ValueError(f"ambiguous active rate-limit policies for path {path!r}")
    return best[0]
