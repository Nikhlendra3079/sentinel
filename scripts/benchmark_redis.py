"""Benchmark Redis-backed rate-limit decisions.

Example:
  python scripts/benchmark_redis.py --redis-url redis://localhost:6379/15 \\
      --requests 5000 --concurrency 100

Use a dedicated Redis database. Each run uses fresh random tenant/policy IDs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
import uuid
from types import SimpleNamespace

from redis.asyncio import Redis

from app.limiter.redis_engine import RedisRateLimitEngine


def percentile(samples: list[float], percentile_value: float) -> float:
    ordered = sorted(samples)
    if not ordered:
        return 0.0
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


async def benchmark_algorithm(
    engine: RedisRateLimitEngine,
    algorithm: str,
    *,
    requests: int,
    concurrency: int,
    limit: int,
    window_seconds: int,
) -> dict[str, float | int | str]:
    policy = SimpleNamespace(
        id=uuid.uuid4(),
        version=1,
        algorithm=algorithm,
        limit_count=limit,
        window_seconds=window_seconds,
        burst_capacity=limit,
    )
    tenant_id = uuid.uuid4()
    # Prime SCRIPT LOAD/EVALSHA before measuring steady-state calls.
    await engine.consume(tenant_id=tenant_id, policy=policy)
    semaphore = asyncio.Semaphore(concurrency)
    latencies_ms: list[float] = []
    allowed = 0

    async def one_request() -> None:
        nonlocal allowed
        async with semaphore:
            started = time.perf_counter()
            result = await engine.consume(tenant_id=tenant_id, policy=policy)
            latencies_ms.append((time.perf_counter() - started) * 1000)
            if result.decision.allowed:
                allowed += 1

    started = time.perf_counter()
    await asyncio.gather(*(one_request() for _ in range(requests)))
    elapsed = time.perf_counter() - started

    return {
        "algorithm": algorithm,
        "requests": requests,
        "allowed": allowed,
        "duration_seconds": round(elapsed, 4),
        "throughput_requests_per_second": round(requests / elapsed, 2),
        "latency_ms_p50": round(percentile(latencies_ms, 0.50), 3),
        "latency_ms_p95": round(percentile(latencies_ms, 0.95), 3),
        "latency_ms_p99": round(percentile(latencies_ms, 0.99), 3),
        "latency_ms_mean": round(statistics.fmean(latencies_ms), 3),
        "latency_ms_max": round(max(latencies_ms, default=0.0), 3),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redis-url", default="redis://localhost:6379/15")
    parser.add_argument("--requests", type=int, default=5000)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--window-seconds", type=int, default=60)
    args = parser.parse_args()
    if min(args.requests, args.concurrency, args.limit, args.window_seconds) <= 0:
        parser.error("all numeric arguments must be positive")

    redis = Redis.from_url(
        args.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=5,
    )
    try:
        await redis.ping()
        engine = RedisRateLimitEngine(redis)
        results = []
        for algorithm in ("token_bucket", "fixed_window", "sliding_window"):
            results.append(await benchmark_algorithm(
                engine,
                algorithm,
                requests=args.requests,
                concurrency=args.concurrency,
                limit=args.limit,
                window_seconds=args.window_seconds,
            ))
        print(json.dumps({
            "redis_url": args.redis_url.split("@")[-1],
            "concurrency": args.concurrency,
            "results": results,
            "note": "Run on an otherwise idle machine; compare repeated runs, not one sample.",
        }, indent=2))
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
