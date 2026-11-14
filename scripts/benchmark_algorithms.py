"""Repeatable microbenchmark for Sentinel's in-process and Redis algorithms.

Examples (PowerShell):
  python scripts/benchmark_algorithms.py --iterations 20000 --concurrency 8
  python scripts/benchmark_algorithms.py --iterations 5000 --concurrency 16 `
      --redis-url redis://localhost:6379/15

This is a controlled microbenchmark, not a substitute for end-to-end Locust
load tests. Run against an otherwise idle machine and record the environment.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import statistics
import time
import uuid
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.limiter.fixed_window import FixedWindowConfig, FixedWindowLimiter
from app.limiter.sliding_window import SlidingWindowLogConfig, SlidingWindowLogLimiter
from app.limiter.token_bucket import TokenBucketConfig, TokenBucketLimiter


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def summarize(name: str, backend: str, latencies: list[float], elapsed: float,
              allowed: int, errors: int, concurrency: int) -> dict:
    count = len(latencies)
    return {
        "name": name,
        "backend": backend,
        "requests": count,
        "concurrency": concurrency,
        "elapsed_seconds": round(elapsed, 6),
        "throughput_requests_per_second": round(count / elapsed, 2) if elapsed else 0,
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50) * 1000, 4),
            "p95": round(percentile(latencies, 0.95) * 1000, 4),
            "p99": round(percentile(latencies, 0.99) * 1000, 4),
            "mean": round(statistics.fmean(latencies) * 1000, 4) if latencies else 0,
        },
        "allowed": allowed,
        "errors": errors,
    }


def run_local(
    name: str,
    limiter,
    iterations: int,
    concurrency: int,
    warmup: int,
    key_count: int,
) -> dict:
    def key_for(index: int) -> str:
        return f"benchmark:key:{index % key_count}"

    # Warm up using the same key distribution as the measured workload.
    for i in range(warmup):
        warmup_key = f"benchmark:warmup:{i % key_count}"
        limiter.consume(warmup_key)

    latencies: list[float] = []
    allowed = 0
    errors = 0

    def operation(index):
        started = time.perf_counter()
        try:
            result = limiter.consume(key_for(index))
            return time.perf_counter() - started, result.allowed, False
        except Exception:
            return time.perf_counter() - started, False, True

    started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for duration, was_allowed, failed in executor.map(
            operation, range(iterations)
        ):
            latencies.append(duration)
            allowed += int(was_allowed)
            errors += int(failed)

    elapsed = time.perf_counter() - started

    state_count = getattr(
        limiter, "key_count", getattr(limiter, "bucket_count", lambda: 0)
    )()

    return {
        **summarize(
            name, "in_process", latencies, elapsed,
            allowed, errors, concurrency
        ),
        "key_count_configured": key_count,
        "state_count_retained": state_count,
        "lock_count_retained": len(limiter._locks),
    }


async def run_redis(name: str, redis_url: str, iterations: int, concurrency: int, warmup: int) -> dict:
    from redis.asyncio import Redis
    from app.limiter.redis_engine import RedisRateLimitEngine

    client = Redis.from_url(redis_url, decode_responses=True)
    policy = SimpleNamespace(
        id=uuid.uuid4(), version=1, algorithm=name, limit_count=iterations + 1,
        window_seconds=3600, burst_capacity=iterations + 1,
    )
    engine = RedisRateLimitEngine(client)
    tenant_id = uuid.uuid4()
    warmup_tenant_id = uuid.uuid4()
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    allowed = 0
    errors = 0

    async def operation():
        nonlocal allowed, errors
        async with semaphore:
            started = time.perf_counter()
            try:
                result = await engine.consume(tenant_id=tenant_id, policy=policy)
                latencies.append(time.perf_counter() - started)
                allowed += int(result.decision.allowed)
            except Exception:
                latencies.append(time.perf_counter() - started)
                errors += 1

    try:
        await client.ping()
        for _ in range(warmup):
            await engine.consume(tenant_id=warmup_tenant_id, policy=policy)
        started = time.perf_counter()
        await asyncio.gather(*(operation() for _ in range(iterations)))
        elapsed = time.perf_counter() - started
        return summarize(name, "redis", latencies, elapsed, allowed, errors, concurrency)
    finally:
        await client.aclose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20000)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--warmup", type=int, default=1000)
    parser.add_argument("--key-count", type=int, default=1)
    parser.add_argument("--redis-url", default=os.getenv("SENTINEL_BENCH_REDIS_URL"))
    parser.add_argument("--output", default="artifacts/benchmark-results.json")
    args = parser.parse_args()
    if (
        args.iterations < 1
        or args.concurrency < 1
        or args.warmup < 0
        or args.key_count < 1
    ):
        parser.error("iterations/concurrency must be positive and warmup non-negative")

    limit = args.iterations + 1
    local = [
        ("token_bucket", TokenBucketLimiter(TokenBucketConfig(limit, 1_000_000))),
        ("fixed_window", FixedWindowLimiter(FixedWindowConfig(limit, 3600))),
        ("sliding_window", SlidingWindowLogLimiter(SlidingWindowLogConfig(limit, 3600))),
    ]
    results = [
        run_local(
            name,
            limiter,
            args.iterations,
            args.concurrency,
            args.warmup,
            args.key_count,
        )
        for name, limiter in local
    ]
    if args.redis_url:
        for name in ("token_bucket", "fixed_window", "sliding_window"):
            results.append(asyncio.run(run_redis(
                name, args.redis_url, args.iterations, args.concurrency, args.warmup
            )))

    report = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "configuration": {
            "iterations": args.iterations,
            "key_count": args.key_count,
            "concurrency": args.concurrency,
            "warmup_requests_per_case": args.warmup,
            "redis_included": bool(args.redis_url),
        },
        "results": results,
        "notes": [
            "Microbenchmark results are environment-specific; compare only under controlled conditions.",
            "In-process algorithms use one hot key and include Python lock contention.",
            "Redis results include client, network, Redis scheduling, and Lua execution latency.",
            "This benchmark is not an HTTP end-to-end load test.",
        ],
    }
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))
    print(f"\nSaved benchmark report: {args.output}")


if __name__ == "__main__":
    main()
