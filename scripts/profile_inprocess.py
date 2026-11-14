"""Profile Python-side in-process token-bucket overhead with cProfile."""
from __future__ import annotations

import argparse
import cProfile
import pstats
import time

from app.limiter.token_bucket import TokenBucketConfig, TokenBucketLimiter


def workload(iterations: int) -> None:
    limiter = TokenBucketLimiter(TokenBucketConfig(capacity=iterations + 1, refill_rate=1))
    for index in range(iterations):
        limiter.consume(f"tenant-{index % 100}:policy-1")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=1_000_000)
    parser.add_argument("--output", default="sentinel-profile.prof")
    args = parser.parse_args()
    profiler = cProfile.Profile()
    started = time.perf_counter()
    profiler.enable()
    workload(args.iterations)
    profiler.disable()
    elapsed = time.perf_counter() - started
    profiler.dump_stats(args.output)
    print(f"iterations={args.iterations} elapsed_seconds={elapsed:.4f}")
    print(f"profile_saved={args.output}")
    pstats.Stats(profiler).strip_dirs().sort_stats("cumulative").print_stats(25)


if __name__ == "__main__":
    main()
