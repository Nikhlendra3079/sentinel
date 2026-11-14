"""Profile the in-process algorithm implementations with cProfile.

PowerShell:
  python scripts/profile_in_process.py --iterations 100000 --algorithm sliding_window
"""
import argparse
import cProfile
import pstats
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.limiter.fixed_window import FixedWindowConfig, FixedWindowLimiter
from app.limiter.sliding_window import SlidingWindowLogConfig, SlidingWindowLogLimiter
from app.limiter.token_bucket import TokenBucketConfig, TokenBucketLimiter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100000)
    parser.add_argument("--algorithm", choices=["token_bucket", "fixed_window", "sliding_window"],
                        default="token_bucket")
    parser.add_argument("--profile-output", default="artifacts/sentinel-profile.prof")
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args()

    if args.iterations < 1:
        parser.error("iterations must be positive")

    limit = args.iterations + 1
    if args.algorithm == "token_bucket":
        limiter = TokenBucketLimiter(TokenBucketConfig(limit, 1_000_000))
    elif args.algorithm == "fixed_window":
        limiter = FixedWindowLimiter(FixedWindowConfig(limit, 3600))
    else:
        limiter = SlidingWindowLogLimiter(SlidingWindowLogConfig(limit, 3600))

    def workload():
        for _ in range(args.iterations):
            limiter.consume("profile:hot-key")

    profiler = cProfile.Profile()
    started = time.perf_counter()
    profiler.enable()
    workload()
    profiler.disable()
    elapsed = time.perf_counter() - started

    import os
    os.makedirs("artifacts", exist_ok=True)
    profiler.dump_stats(args.profile_output)
    print(f"algorithm={args.algorithm} iterations={args.iterations} elapsed={elapsed:.4f}s")
    pstats.Stats(profiler).strip_dirs().sort_stats("cumulative").print_stats(args.top)
    print(f"Profile saved: {args.profile_output}")


if __name__ == "__main__":
    main()
