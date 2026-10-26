"""Credential-free HTTP measurements against immutable authored expectations.

This evaluates fixture contracts, not human agreement or general model quality.
"""

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

METHODS = ("keyword", "vector", "hybrid", "reranked")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_seed(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise ValueError("Seed manifest schema_version must be 1")
    url = urlsplit(value.get("api_url", ""))
    if url.scheme != "http" or url.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Evaluation requires an explicit loopback HTTP API")
    if url.username or url.password or url.query or url.fragment:
        raise ValueError("API URL must not contain credentials, query or fragment")
    for name in ("profile", "principals", "documents"):
        if not isinstance(value.get(name), dict):
            raise ValueError(f"Seed manifest requires {name}")
    return value


def request_json(
    seed: dict[str, Any],
    principal: str,
    path: str,
    body: dict[str, Any] | None = None,
    timeout: float = 60,
) -> tuple[int, dict[str, Any], float]:
    identity = seed["principals"].get(principal)
    if not identity or not identity.get("api_key"):
        raise ValueError(f"Missing credential for principal alias {principal}")
    request = Request(
        seed["api_url"].rstrip("/") + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-API-Key": identity["api_key"], "Content-Type": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read())
            return response.status, result, (time.perf_counter() - started) * 1000
    except HTTPError as exc:
        # Preserve status, not raw error text: middleware/errors may echo secrets.
        return (
            exc.code,
            {"error": "HTTP request rejected"},
            (time.perf_counter() - started) * 1000,
        )
    except (URLError, TimeoutError, OSError):
        return (
            0,
            {"error": "API unavailable or timed out"},
            (time.perf_counter() - started) * 1000,
        )


def score_case(
    case: dict[str, Any],
    response: dict[str, Any],
    status: int,
    documents: dict[str, Any],
) -> dict[str, Any]:
    """Check ranks and immutable passages; mentions never establish support."""
    reverse = {str(v["document_id"]): k for k, v in documents.items()}
    trace = response.get("retrieval_trace") or {}
    ranks = trace.get("scores") or []
    citations = response.get("sources") or []

    def identity(item: dict[str, Any]) -> tuple[str | None, int | None]:
        version = item.get("document_version", item.get("version_number"))
        return reverse.get(str(item.get("document_id"))), version

    expected = {
        (s["document_id"], s["version_number"]) for s in case["expected_sources"]
    }
    forbidden = {
        (s["document_id"], s["version_number"]) for s in case["forbidden_sources"]
    }
    retrieved = [identity(item) for item in ranks[:5]]
    exposed = set(retrieved) | {identity(item) for item in citations}
    # An unknown version of a forbidden document cannot be treated as safe.
    forbidden_ids = {doc for doc, _ in forbidden}
    unauthorized = sum(
        item in forbidden or (item[0] in forbidden_ids and item[1] is None)
        for item in exposed
    )
    hits = expected & set(retrieved)
    reciprocal = next(
        (1 / rank for rank, item in enumerate(retrieved, 1) if item in expected),
        0.0,
    )
    refused = bool(response.get("refused")) or response.get("outcome") == "refused"
    behavior = case["expected_behavior"]
    transport_ok = status == 200 or (behavior == "deny" and status in (403, 404))
    if behavior == "deny":
        correct_behavior = status in (403, 404) or (
            status == 200 and refused and not response.get("answer") and not citations
        )
    elif behavior in ("review", "refuse"):
        correct_behavior = status == 200 and refused
    else:
        correct_behavior = (
            status == 200 and not refused and bool(response.get("answer"))
        )

    valid_citations = 0
    for source in case["expected_sources"]:
        logical = source["document_id"]
        version = str(source["version_number"])
        snapshot = documents[logical].get("versions", {}).get(version, {})
        for citation in citations:
            if identity(citation) != (logical, source["version_number"]):
                continue
            passage = citation.get("quoted_text")
            if (
                isinstance(passage, str)
                and source["quoted_text"] in passage
                and passage in snapshot.get("content", "")
                and citation.get("content_hash") == snapshot.get("content_hash")
                and snapshot.get("content_hash") is not None
            ):
                valid_citations += 1
                break

    source_correct = valid_citations == len(expected) if expected else None
    passed = transport_ok and correct_behavior and unauthorized == 0
    if expected:
        passed = passed and bool(source_correct)
        passed = passed and all(
            source["quoted_text"].casefold()
            in (response.get("answer") or "").casefold()
            for source in case["expected_sources"]
        )
    return {
        "case_id": case["id"],
        "category": case["category"],
        "http_status": status,
        "passed": passed,
        "behavior_correct": correct_behavior,
        "refused": refused,
        "recall_at_5": len(hits) / len(expected) if expected else None,
        "reciprocal_rank": reciprocal if expected else None,
        "source_version_correct": source_correct,
        "unauthorized_source_exposures": unauthorized,
        "refusal_false_positive": behavior == "answer" and refused,
        "refusal_false_negative": behavior in ("refuse", "review", "deny")
        and not correct_behavior
        and status == 200,
        "execution_error": not transport_ok,
        "query_id": response.get("id"),
        "retrieved": [
            {"document_id": doc, "version_number": ver} for doc, ver in retrieved
        ],
        "provenance": response.get("provenance"),
        "retrieval_trace": trace,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def mean(key: str) -> float | None:
        values = [row[key] for row in rows if row.get(key) is not None]
        return sum(values) / len(values) if values else None

    return {
        "cases": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "failed": sum(not row["passed"] for row in rows),
        "recall_at_5": mean("recall_at_5"),
        "mrr": mean("reciprocal_rank"),
        "source_version_correctness": mean("source_version_correct"),
        "refusal_false_positives": sum(row["refusal_false_positive"] for row in rows),
        "refusal_false_negatives": sum(row["refusal_false_negative"] for row in rows),
        "unauthorized_source_exposures": sum(
            row["unauthorized_source_exposures"] for row in rows
        ),
        "execution_errors": sum(row["execution_error"] for row in rows),
    }


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile; raw observations accompany every summary."""
    if not values:
        raise ValueError("Percentile requires observations")
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]
