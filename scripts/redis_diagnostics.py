"""Aggregate diagnostics for Sentinel's Redis rate-limit keys.

Does not print tenant IDs or raw Redis keys. It reports key counts, memory use,
and TTL distribution so expiry leaks can be spotted without exposing identifiers.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redis.asyncio import Redis


async def inspect(redis_url: str):
    client = Redis.from_url(redis_url, decode_responses=True)
    try:
        info = await client.info("memory")
        count = 0
        memory_bytes = 0
        ttl_missing = 0
        ttl_min = None
        ttl_max = None
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor=cursor, match="sentinel:rl:*", count=500)
            for key in keys:
                count += 1
                usage = await client.memory_usage(key)
                if usage is not None:
                    memory_bytes += usage
                ttl = await client.pttl(key)
                if ttl == -1:
                    ttl_missing += 1
                elif ttl >= 0:
                    ttl_min = ttl if ttl_min is None else min(ttl_min, ttl)
                    ttl_max = ttl if ttl_max is None else max(ttl_max, ttl)
            if cursor == 0:
                break
        print(json.dumps({
            "rate_limit_key_count": count,
            "rate_limit_memory_bytes": memory_bytes,
            "rate_limit_memory_mib": round(memory_bytes / (1024 * 1024), 3),
            "keys_without_expiry": ttl_missing,
            "ttl_min_ms": ttl_min,
            "ttl_max_ms": ttl_max,
            "redis_used_memory_bytes": info.get("used_memory"),
            "redis_used_memory_peak_bytes": info.get("used_memory_peak"),
            "redis_maxmemory_bytes": info.get("maxmemory"),
        }, indent=2))
    finally:
        await client.aclose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis-url", default=os.getenv("SENTINEL_REDIS_URL",
                                                          "redis://localhost:6379/0"))
    args = parser.parse_args()
    asyncio.run(inspect(args.redis_url))


if __name__ == "__main__":
    main()
