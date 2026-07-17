#!/usr/bin/env python3
"""Simple load test (spec §12 Phase 7).

Drives the guest→session→message flow concurrently against a running API.
With no ANTHROPIC_API_KEY on the server, turns exercise the full pipeline
in degraded-sentinel mode (rules layer + fallback reply) — which is exactly
the hot path that must stay fast.

Usage: python load_test.py [--base http://localhost:8000] [--users 20] [--turns 3]
"""

import argparse
import asyncio
import statistics
import sys
import time
import uuid

import httpx


async def one_user(base: str, turns: int, latencies: list, errors: list) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=30) as client:
        try:
            resp = await client.post(
                "/auth/guest",
                json={
                    "device_guest_id": uuid.uuid4().hex,
                    "nickname": "load",
                    "locale": "ar",
                    "attested_adult": True,
                },
            )
            token = resp.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            session = (await client.post("/chat/sessions", headers=headers)).json()
            for i in range(turns):
                started = time.monotonic()
                r = await client.post(
                    f"/chat/sessions/{session['id']}/messages",
                    headers=headers,
                    json={"content": f"رسالة اختبار رقم {i} — اليوم كان مزدحماً"},
                )
                elapsed = time.monotonic() - started
                if r.status_code == 200:
                    latencies.append(elapsed)
                else:
                    errors.append(r.status_code)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--turns", type=int, default=3)
    args = parser.parse_args()

    latencies: list[float] = []
    errors: list = []
    started = time.monotonic()
    await asyncio.gather(*(one_user(args.base, args.turns, latencies, errors) for _ in range(args.users)))
    wall = time.monotonic() - started

    total = args.users * args.turns
    print(f"turns: {len(latencies)}/{total} ok, {len(errors)} errors, wall {wall:.1f}s")
    if latencies:
        print(
            f"latency p50={statistics.median(latencies)*1000:.0f}ms "
            f"p95={sorted(latencies)[int(len(latencies)*0.95)-1]*1000:.0f}ms "
            f"max={max(latencies)*1000:.0f}ms"
        )
    if errors:
        print(f"errors: {errors[:5]}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
