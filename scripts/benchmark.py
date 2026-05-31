#!/usr/bin/env python3
"""Benchmark script for GroundTruth performance testing."""

import asyncio
import time
import statistics
from typing import Any

import httpx


BASE_URL = "http://localhost:8000"


async def benchmark_endpoint(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    iterations: int = 100,
    **kwargs: Any,
) -> dict[str, Any]:
    """Benchmark an API endpoint."""
    latencies: list[float] = []
    errors = 0

    for _ in range(iterations):
        start = time.perf_counter()
        try:
            response = await client.request(method, f"{BASE_URL}{path}", **kwargs)
            response.raise_for_status()
        except Exception:
            errors += 1
        finally:
            latencies.append((time.perf_counter() - start) * 1000)

    return {
        "endpoint": f"{method} {path}",
        "iterations": iterations,
        "errors": errors,
        "min_ms": round(min(latencies), 2),
        "max_ms": round(max(latencies), 2),
        "mean_ms": round(statistics.mean(latencies), 2),
        "p50_ms": round(statistics.median(latencies), 2),
        "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 2),
        "p99_ms": round(sorted(latencies)[int(len(latencies) * 0.99)], 2),
    }


async def main() -> None:
    """Run all benchmarks."""
    async with httpx.AsyncClient() as client:
        results = []

        # Health check
        results.append(await benchmark_endpoint(client, "GET", "/api/health"))

        # List documents
        results.append(await benchmark_endpoint(client, "GET", "/api/documents"))

        # Print results
        print("\n" + "=" * 80)
        print("GroundTruth Performance Benchmarks")
        print("=" * 80)

        for r in results:
            print(f"\n{r['endpoint']}")
            print(f"  Iterations: {r['iterations']} | Errors: {r['errors']}")
            print(f"  Latency: min={r['min_ms']}ms, mean={r['mean_ms']}ms, max={r['max_ms']}ms")
            print(f"  Percentiles: p50={r['p50_ms']}ms, p95={r['p95_ms']}ms, p99={r['p99_ms']}ms")

        print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
