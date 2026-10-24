#!/usr/bin/env python3
"""Measure actual HTTP queries against preseeded, independently counted chunks.

Never manufactures a 100k corpus or extrapolates portable timings to PostgreSQL.
"""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from app.portfolio.evaluation import METHODS, percentile, read_seed, request_json
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import create_async_engine


async def inspect_database(
    database_url: str, datasets: list[dict], portable: bool
) -> dict:
    engine = create_async_engine(database_url)
    try:
        dialect = engine.dialect.name
        if not portable and dialect != "postgresql":
            raise ValueError("Indexed matrix requires a real PostgreSQL database")
        observations = {"dialect": dialect, "datasets": [], "indexes": []}
        async with engine.connect() as connection:
            for dataset in datasets:
                ids = dataset["document_ids"]
                if not ids or len(ids) != len(set(ids)):
                    raise ValueError("Dataset requires unique actual document IDs")
                count_query = text(
                    "SELECT count(*) FROM chunks WHERE document_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True))
                # UUID text binds are portable across SQLite and PostgreSQL drivers.
                if dialect == "sqlite":
                    ids = [value.replace("-", "") for value in ids]
                count = (
                    await connection.execute(count_query, {"ids": ids})
                ).scalar_one()
                if count != dataset["chunk_count"]:
                    raise ValueError(
                        f"Actual chunk count {count} differs from "
                        f"declared {dataset['chunk_count']}"
                    )
                observations["datasets"].append(
                    {"chunk_count": count, "documents": len(ids)}
                )
            if dialect == "postgresql":
                vector = (
                    await connection.execute(
                        text(
                            "SELECT extversion FROM pg_extension WHERE extname='vector'"
                        )
                    )
                ).scalar_one_or_none()
                indexes = (
                    await connection.execute(
                        text(
                            "SELECT indexname,indexdef FROM pg_indexes "
                            "WHERE tablename='chunks'"
                        )
                    )
                ).all()
                observations["pgvector_version"] = vector
                observations["indexes"] = [
                    {"name": row[0], "definition": row[1]} for row in indexes
                ]
                definitions = " ".join(row[1].lower() for row in indexes)
                if not portable and (
                    not vector or "hnsw" not in definitions or "gin" not in definitions
                ):
                    raise ValueError(
                        "Actual chunk HNSW and full-text GIN indexes are required"
                    )
        return observations
    finally:
        await engine.dispose()


def prepare_measurement(seed, args):
    datasets = seed.get("benchmark", {}).get("datasets", [])
    if not datasets:
        raise ValueError("No actual preseeded benchmark datasets in manifest")
    database_url = os.environ.get("GROUNDTRUTH_BENCHMARK_DATABASE_URL")
    if not database_url:
        raise ValueError(
            "GROUNDTRUTH_BENCHMARK_DATABASE_URL required for count verification"
        )
    if not args.portable and sorted(d["chunk_count"] for d in datasets) != [
        1000,
        10000,
        100000,
    ]:
        raise ValueError("Full matrix requires exactly 1k/10k/100k actual chunks")
    if not args.portable and (
        seed["profile"].get("persistence") != "postgresql" or not args.query_plan_file
    ):
        raise ValueError(
            "PostgreSQL profile and natural query-plan evidence required; "
            "unavailable without live infrastructure"
        )
    database = asyncio.run(inspect_database(database_url, datasets, args.portable))
    plans = None
    if args.query_plan_file:
        plans = json.loads(args.query_plan_file.read_text(encoding="utf-8"))
        if plans.get("forced_planner_settings") or not plans.get("natural_plans"):
            raise ValueError("Natural, unforced application plans are required")
    return datasets, database, plans


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--portable",
        action="store_true",
        help="Nonindexed smoke measurement; never the indexed acceptance matrix",
    )
    parser.add_argument("--query-plan-file", type=Path)
    args = parser.parse_args()
    try:
        seed = read_seed(args.seed_manifest)
        datasets, database, plans = prepare_measurement(seed, args)
        measured, warmup, repeats = (10, 2, 1) if args.portable else (100, 20, 3)
        concurrency_values = (1,) if args.portable else (1, 10)
        rows = []
        for dataset in datasets:
            principal = dataset.get("principal", "operator-a")
            questions = dataset.get("questions", [])
            if not questions:
                raise ValueError("Dataset requires authored benchmark questions")
            for method in METHODS:
                for concurrency in concurrency_values:
                    for repeat in range(repeats):

                        def query(
                            index,
                            principal=principal,
                            questions=questions,
                            document_ids=dataset["document_ids"],
                            method=method,
                        ):
                            status, response, elapsed = request_json(
                                seed,
                                principal,
                                "/api/queries",
                                {
                                    "question": questions[index % len(questions)],
                                    "document_ids": document_ids,
                                    "retrieval_method": method,
                                    "top_k": 5,
                                },
                            )
                            trace = response.get("retrieval_trace") or {}
                            if not args.portable and status == 200:
                                actual = (response.get("provenance") or {}).get("index")
                                if actual not in {
                                    "postgresql-indexed",
                                    "postgresql-hnsw-fts",
                                }:
                                    raise ValueError(
                                        "API did not attest actual indexed retrieval"
                                    )
                            return {
                                "sequence": index,
                                "http_status": status,
                                "application_elapsed_ms": elapsed,
                                "retrieval_elapsed_ms": trace.get(
                                    "retrieval_latency_ms", trace.get("retrieval_ms")
                                ),
                                "refused": response.get("refused"),
                                "outcome": response.get("outcome"),
                                "provenance": response.get("provenance"),
                                "cache": trace.get("cache"),
                                "query_id": response.get("id"),
                            }

                        with ThreadPoolExecutor(max_workers=concurrency) as pool:
                            warm = list(pool.map(query, range(warmup)))
                            started = time.perf_counter()
                            samples = list(pool.map(query, range(measured)))
                            elapsed = time.perf_counter() - started
                        values = [s["application_elapsed_ms"] for s in samples]
                        retrieval = [
                            s["retrieval_elapsed_ms"]
                            for s in samples
                            if s["retrieval_elapsed_ms"] is not None
                        ]
                        rows.append(
                            {
                                "chunk_count": dataset["chunk_count"],
                                "method": method,
                                "concurrency": concurrency,
                                "repeat": repeat + 1,
                                "warmup": warm,
                                "samples": samples,
                                "errors": sum(s["http_status"] != 200 for s in samples),
                                "application_p50_ms": percentile(values, 0.5),
                                "application_p95_ms": percentile(values, 0.95),
                                "retrieval_p50_ms": percentile(retrieval, 0.5)
                                if retrieval
                                else None,
                                "retrieval_p95_ms": percentile(retrieval, 0.95)
                                if retrieval
                                else None,
                                "throughput_requests_second": measured / elapsed,
                            }
                        )
        report = {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "measurement_scope": "portable_nonindexed_smoke"
            if args.portable
            else "postgresql_indexed_matrix",
            "cache_scope": (
                "Warm runs; no cold operating-system cache claim. "
                "First-after-restart requires separate explicit observations."
            ),
            "hardware": {
                "platform": platform.platform(),
                "processor": platform.processor(),
                "cpu_count": os.cpu_count(),
                "python": platform.python_version(),
            },
            "profile": seed["profile"],
            "database": database,
            "query_plan_sha256": hashlib.sha256(
                args.query_plan_file.read_bytes()
            ).hexdigest()
            if args.query_plan_file
            else None,
            "query_plans": plans,
            "rows": rows,
        }
        body = (json.dumps(report, indent=2) + "\n").encode()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(body)
        args.output.with_suffix(args.output.suffix + ".sha256").write_text(
            hashlib.sha256(body).hexdigest() + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "conditions": len(rows),
                    "scope": report["measurement_scope"],
                }
            )
        )
        return int(any(row["errors"] for row in rows))
    except Exception as exc:
        # Do not print exception text: a database driver may include its connection URL.
        print(
            json.dumps(
                {
                    "status": "unavailable",
                    "error_type": type(exc).__name__,
                    "reason": (
                        "Check infrastructure, actual dataset counts, indexes "
                        "and natural query plans. No indexed results produced."
                    ),
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
