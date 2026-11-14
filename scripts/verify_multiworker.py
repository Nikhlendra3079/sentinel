"""Verify that multiple API workers share one Redis quota.

Start the API with --workers 4 and create a fresh fixed-window policy with
limit_count=10. Then run:
  python scripts/verify_multiworker.py --api-key <key> --requests 50 --expected-allowed 10
"""
from __future__ import annotations

import argparse
import asyncio
import json

import httpx


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--expected-allowed", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=50)
    args = parser.parse_args()

    semaphore = asyncio.Semaphore(args.concurrency)
    headers = {"Authorization": f"Bearer {args.api_key}"}
    statuses: list[int] = []

    async with httpx.AsyncClient(base_url=args.base_url, timeout=10) as client:
        async def one() -> None:
            async with semaphore:
                response = await client.get("/api/v1/protected/ping", headers=headers)
                statuses.append(response.status_code)

        await asyncio.gather(*(one() for _ in range(args.requests)))

    allowed = statuses.count(200)
    denied = statuses.count(429)
    other = {status: statuses.count(status) for status in set(statuses) if status not in (200, 429)}
    report = {
        "requests": len(statuses),
        "allowed_200": allowed,
        "denied_429": denied,
        "other_statuses": other,
        "expected_allowed": args.expected_allowed,
        "passed": allowed == args.expected_allowed and denied == args.requests - args.expected_allowed and not other,
    }
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
