from app.limiter.token_bucket import TokenBucketConfig


def token_bucket_config_from_policy(
    *,
    limit_count: int,
    window_seconds: int,
    burst_capacity: int | None,
) -> TokenBucketConfig:
    """Translate the current database policy fields into token-bucket units.

    `limit_count / window_seconds` is the average refill rate. If no explicit
    burst_capacity is configured, limit_count is used as the bucket capacity.
    """
    if limit_count <= 0:
        raise ValueError("limit_count must be greater than zero")
    if window_seconds <= 0:
        raise ValueError("window_seconds must be greater than zero")
    capacity = burst_capacity if burst_capacity is not None else limit_count
    return TokenBucketConfig(
        capacity=float(capacity),
        refill_rate=limit_count / window_seconds,
    )
